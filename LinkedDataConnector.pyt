import arcpy
import os
import json
import requests
import re
import os
import collections
import datetime
import numpy
from sets import Set
from collections import OrderedDict
from collections import defaultdict
from collections import namedtuple
from decimal import Decimal
from arcpy import env

class Toolbox(object):
	def __init__(self):
		"""Define the toolbox (the name of the toolbox is the name of the
		.pyt file)."""
		self.label = "Toolbox"
		self.alias = ""

		# List of tool classes associated with this toolbox
		self.tools = [LinkedDataSpatialQuery, LinkedDataPropertyEnrich, MergeBatchNoFunctionalProperty, MergeSingleNoFunctionalProperty, LocationPropertyPath, RelFinder]


class LinkedDataSpatialQuery(object):
	def __init__(self):
		"""Define the tool (tool name is the name of the class)."""
		self.label = "Linked Data Spatial Query"
		self.description = "Get geographic features from wikidata by mouse clicking. The Place type can be specified."
		self.canRunInBackground = False
		self.entityTypeURLList = []
		self.entityTypeLabel = []
		self.enterTypeText = ""

	def getParameterInfo(self):
		"""Define parameter definitions"""
		# interactively draw feature on the map
		in_buf_query_center = arcpy.Parameter(
			displayName="Input Buffer Query Center",
			name="in_buf_query_center",
			datatype="GPFeatureRecordSetLayer",
			parameterType="Required",
			direction="Input")

		# Use __file__ attribute to find the .lyr file (assuming the
		#  .pyt and .lyr files exist in the same folder)
		in_buf_query_center.value = os.path.join(os.path.dirname(__file__),"symbology.lyr")
		in_buf_query_center.filter.list = ["Point"]

		# Choose place type for search
		in_place_type = arcpy.Parameter(
			displayName="Input Place Type",
			name="in_place_type",
			datatype="GPString",
			parameterType="Optional",
			direction="Input")

		in_place_type.filter.type = "ValueList"
		in_place_type.filter.list = []

		# Choose place type for search
		in_is_directed_instance = arcpy.Parameter(
			displayName="Disable Transitive Subclass Reasoning",
			name="in_is_directed_instance",
			datatype="GPBoolean",
			parameterType="Optional",
			direction="Input")

		in_is_directed_instance.value = False

		# Search Radius
		in_radius = arcpy.Parameter(
			displayName="Input Search Radius (mile)",
			name="in_radius",
			datatype="GPString",
			parameterType="Required",
			direction="Input")

		in_radius.value = "10"

		out_location = arcpy.Parameter(
			displayName="Output Location",
			name="out_location",
			datatype="DEWorkspace",
			parameterType="Required",
			direction="Input")

		out_location.value = os.path.dirname(__file__)

		# Derived Output Point Feature Class Name
		out_points_name = arcpy.Parameter(
			displayName="Output Point Feature Class Name",
			name="out_points_name",
			datatype="GPString",
			parameterType="Required",
			direction="Input")

		# out_features.parameterDependencies = [in_buf_query_center.name]
		# out_features.schema.clone = True

		out_place_type_url = arcpy.Parameter(
			displayName="Output Place Type URL",
			name="out_place_type_url",
			datatype="GPString",
			parameterType="Derived",
			direction="Output")

		out_place_type_url.value = ""
		# out_place_type_url.parameterDependencies = [in_place_type.name]

		params = [in_buf_query_center, in_place_type, in_is_directed_instance, in_radius, out_location, out_points_name, out_place_type_url]

		return params



	def isLicensed(self):
		"""Set whether tool is licensed to execute."""
		return True

	def updateParameters(self, parameters):
		"""Modify the values and properties of parameters before internal
		validation is performed.  This method is called whenever a parameter
		has been changed."""
		in_buf_query_center = parameters[0]
		in_place_type = parameters[1]
		in_is_directed_instance = parameters[2]
		in_radius = parameters[3]
		out_location = parameters[4]
		out_points_name = parameters[5]
		out_place_type_url = parameters[6]

		outLocation = out_location.valueAsText
		outFeatureClassName = out_points_name.valueAsText
		
		arcpy.env.workspace = outLocation

		if out_points_name.value and arcpy.Exists(os.path.join(outLocation, outFeatureClassName)):
			arcpy.AddError("The Output Point Feature Class Name already exists in the current workspace!")
			raise arcpy.ExecuteError

		if in_place_type.value:
			enterTypeText = in_place_type.valueAsText
			if "(" in enterTypeText:
				lastIndex = enterTypeText.rfind("(")
				placeType = enterTypeText[:lastIndex]
			else:
				placeType = enterTypeText
			# messages.addMessage("Use Input Type: {0}.".format(in_place_type.valueAsText))
			queryPrefix = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
										PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
										PREFIX wdt: <http://www.wikidata.org/prop/direct/>"""

			entityTypeQuery = queryPrefix + """SELECT ?entityType ?entityTypeLabel
											WHERE
											{
											  #?entity wdt:P31 ?entityType.
											  ?entityType wdt:P279* wd:Q2221906.
											  # retrieve the English label
											  ?entityType rdfs:label  ?entityTypeLabel .
											  FILTER (LANG(?entityTypeLabel) = "en")
											  FILTER REGEX(?entityTypeLabel, '""" + placeType + """')
											  # show results ordered by distance
											}
											"""

			# sparqlParam = {'query':'SELECT ?item ?itemLabel WHERE{ ?item wdt:P31 wd:Q146 . SERVICE wikibase:label { bd:serviceParam wikibase:language "en" }}', 'format':'json'}
			entityTypeSparqlParam = {'query': entityTypeQuery, 'format': 'json'}
			# headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
			sparqlRequest = requests.get('https://query.wikidata.org/sparql', params=entityTypeSparqlParam)
			print(sparqlRequest.url)
			# messages.addMessage("URL: {0}.".format(sparqlRequest.url))
			entityTypeJson = sparqlRequest.json()["results"]["bindings"]

			if len(entityTypeJson) == 0:
				arcpy.AddError("No entity type matches the user's input.")
				raise arcpy.ExecuteError
			else:
				in_place_type.filter.list = [enterTypeText]
				self.entityTypeLabel = []
				self.entityTypeURLList = []
				for jsonItem in entityTypeJson:
					label = jsonItem["entityTypeLabel"]["value"]
					wikiURL = jsonItem["entityType"]["value"]
					wikiURLLastIndex = wikiURL.rfind("/")
					wikiURLLastName = wikiURL[(wikiURLLastIndex+1):]
					self.entityTypeLabel.append(label+"("+"wd:"+wikiURLLastName+")")
					self.entityTypeURLList.append(wikiURL)
					# in_place_type.filter.list.append(jsonItem["entityTypeLabel"]["value"])

				in_place_type.filter.list = in_place_type.filter.list + self.entityTypeLabel

			for i in range(len(self.entityTypeLabel)):
				# messages.addMessage("Label: {0}".format(self.entityTypeLabel[i]))
				if in_place_type.valueAsText == self.entityTypeLabel[i]:
					out_place_type_url.value = self.entityTypeURLList[i]

		return

	def updateMessages(self, parameters):
		"""Modify the messages created by internal validation for each tool
		parameter.  This method is called after internal validation."""
		return

	def execute(self, parameters, messages):
		"""The source code of the tool."""
		in_buf_query_center = parameters[0]
		in_place_type = parameters[1]
		in_is_directed_instance = parameters[2]
		in_radius = parameters[3]
		out_location = parameters[4]
		out_points_name = parameters[5]
		out_place_type_url = parameters[6]

		inBufCenter = in_buf_query_center.valueAsText
		inPlaceType = in_place_type.valueAsText
		searchRadius = in_radius.valueAsText
		outLocation = out_location.valueAsText
		outFeatureClassName = out_points_name.valueAsText
		
		isDirectInstance = False
		
		if in_is_directed_instance.valueAsText == 'true':
			isDirectInstance = True
		elif in_is_directed_instance.valueAsText == 'false':
			isDirectInstance = False

		# arcpy.AddMessage(("in_is_directed_instance.valueAsText: {0}").format(in_is_directed_instance.valueAsText))

	
		if ".gdb" in outLocation:
			# if the outputLocation is a file geodatabase, cancatnate the outputlocation with outFeatureClassName to create a feature class in current geodatabase
			out_path = os.path.join(outLocation,outFeatureClassName)
		else:
			# if the outputLocation is a folder, creats a shapefile in this folder
			out_path = os.path.join(outLocation,outFeatureClassName) + ".shp"
			# however, Relationship Class must be created in a geodatabase, so we forbid to create a shapfile
			# messages.addErrorMessage("Please enter a file geodatabase as output location in order to create a relation class")
			# raise arcpy.ExecuteError
			


		messages.addMessage("outpath: {0}".format(out_path))

		selectedURL = out_place_type_url.valueAsText

		# messages.addMessage("len(self.entityTypeLabel): {0}".format(len(self.entityTypeLabel)))

		# for i in range(len(self.entityTypeLabel)):
		# 	messages.addMessage("Label: {0}".format(self.entityTypeLabel[i]))
		# 	if inPlaceType == self.entityTypeLabel[i]:
		# 		selectedURL = self.entityTypeURLList[i]

		messages.addMessage("selectedURL: {0}".format(selectedURL))

		# Create a FeatureSet object and load in_memory feature class
		in_feature_set = arcpy.FeatureSet()
		in_feature_set.load(inBufCenter)
		in_feature_set_json = json.loads(in_feature_set.JSON)

		# messages.addMessage("Points: {0}".format(json.loads(in_feature_set.JSON)))

		# messages.addMessage("Point: {0}".format(json.loads(in_feature_set.JSON)['spatialReference']['wkid']))

		WGS84Reference = arcpy.SpatialReference(4326)
		currentSpatialReference = arcpy.SpatialReference(in_feature_set_json['spatialReference']['latestWkid'])

		# a set of unique Coordinates for each input points
		# searchCoordsSet = Set()
		searchCoordsSet = []
	
		for i in range(len(in_feature_set_json['features'])):
			lat = in_feature_set_json['features'][i]['geometry']['y']
			lng = in_feature_set_json['features'][i]['geometry']['x']
			coords = [lng, lat]
			searchCoordsSet.append(coords)
		# 	if i == 0:
		# 		searchCoordsSet.append(coords)
		# 	else:
		# 		if coords not in searchCoordsSet:
		# 			searchCoordsSet.add(coords)


		# searchCoordsSet = List(searchCoordsSet)

		# a set of unique Coordinates for each found places
		placeIRISet = Set()
		placeList = []

		for coord in searchCoordsSet:
			lat = coord[1]
			lng = coord[0]

		# lat = in_feature_set_json['features'][0]['geometry']['y']
		# lng = in_feature_set_json['features'][0]['geometry']['x']

			if in_feature_set_json['spatialReference']['wkid'] != '4326' or in_feature_set_json['spatialReference']['latestWkid'] != '4326':
				WGS84PtGeometry = arcpy.PointGeometry(arcpy.Point(lng, lat), currentSpatialReference).projectAs(WGS84Reference)
				# messages.addMessage("My Coordinates: {0}".format(WGS84PtGeometry.WKT))
				coordList = re.split("[( )]", WGS84PtGeometry.WKT)
				lat = coordList[3]
				lng = coordList[2]

			queryPrefix = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
									PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
									PREFIX owl: <http://www.w3.org/2002/07/owl#>
									PREFIX geo-pos: <http://www.w3.org/2003/01/geo/wgs84_pos#>
									PREFIX omgeo: <http://www.ontotext.com/owlim/geo#>
									PREFIX dbpedia: <http://dbpedia.org/resource/>
									PREFIX dbp-ont: <http://dbpedia.org/ontology/>
									PREFIX ff: <http://factforge.net/>
									PREFIX om: <http://www.ontotext.com/owlim/>
									PREFIX wikibase: <http://wikiba.se/ontology#>
									PREFIX bd: <http://www.bigdata.com/rdf#>
									PREFIX wdt: <http://www.wikidata.org/prop/direct/>
									PREFIX geo: <http://www.opengis.net/ont/geosparql#>"""

			if selectedURL != None:
				query = queryPrefix + """SELECT distinct ?place ?placeLabel ?distance ?location
										WHERE {
										# geospatial queries
										SERVICE wikibase:around {
										# get the coordinates of a place
										?place wdt:P625 ?location .
										# create a buffer around (-122.4784360859997 37.81826788900048)
										bd:serviceParam wikibase:center "Point(""" + str(lng) + """ """ + str(lat) + """)"^^geo:wktLiteral .
										# buffer radius 2km
										bd:serviceParam wikibase:radius '"""+searchRadius+"""' .
										bd:serviceParam wikibase:distance ?distance .
										}
										# retrieve the English label
										SERVICE wikibase:label {bd:serviceParam wikibase:language "en". ?place rdfs:label ?placeLabel .}"""
				if isDirectInstance == False:
					query +=			"""?place wdt:P31 ?placeFlatType.
										?placeFlatType wdt:P279* <""" + selectedURL + """>."""
				else:
					query +=			"""?place wdt:P31  <""" + selectedURL + """>."""


										# show results ordered by distance
				query +=				"""} ORDER BY ?distance"""
			else:
				query = queryPrefix + """SELECT distinct ?place ?placeLabel ?distance ?location 
										WHERE {
										# geospatial queries
										SERVICE wikibase:around {
										# get the coordinates of a place
										?place wdt:P625 ?location .
										# create a buffer around (-122.4784360859997 37.81826788900048)
										bd:serviceParam wikibase:center "Point(""" + str(lng) + """ """ + str(lat) + """)"^^geo:wktLiteral .
										# buffer radius 2km
										bd:serviceParam wikibase:radius '"""+searchRadius+"""' .
										bd:serviceParam wikibase:distance ?distance .
										}
										# retrieve the English label
										SERVICE wikibase:label {bd:serviceParam wikibase:language "en". ?place rdfs:label ?placeLabel .}
										?place wdt:P31 ?placeFlatType.
										?placeFlatType wdt:P279* wd:Q2221906.

										# show results ordered by distance
										} ORDER BY ?distance"""

			sparqlParam = {'query': query, 'format': 'json'}
			
			sparqlRequest = requests.get('https://query.wikidata.org/sparql', params=sparqlParam)

			print(sparqlRequest.url)
			messages.addMessage("SPARQL: {0}".format(sparqlRequest.url))
		   
			
			bufferQueryResult = sparqlRequest.json()["results"]["bindings"]

			# if len(bufferQueryResult) == 0:
			# 	messages.addMessage("No {0} nearby the clicked place can be finded!".format(inPlaceType))
			# 	# pythonaddins.MessageBox("No " + inPlaceType + " nearby the clicked place can be finded!",
			# 	#                         "Warning Message", 0)
			# else:

			for item in bufferQueryResult:
				print "%s\t%s\t%s\t%s" % (
					item["place"]["value"], item["placeLabel"]["value"], item["distance"]["value"],
					item["location"]["value"])
				if len(placeIRISet) == 0 or item["place"]["value"] not in placeIRISet:
					placeIRISet.add(item["place"]["value"])
					coordItem = item["location"]["value"]
					coordList = re.split("[( )]", coordItem)
					itemlat = coordList[2]
					itemlng = coordList[1]
					placeList.append(
						[item["place"]["value"], item["placeLabel"]["value"], item["distance"]["value"],
						 itemlat,itemlng])

		if len(placeList) == 0:
			messages.addMessage("No {0} nearby the input point(s) can be finded!".format(inPlaceType))
		else:
			# Spatial reference set to GCS_WGS_1984
			spatial_reference = arcpy.SpatialReference(4326)
			# creat a Point feature class in arcpy
			pt = arcpy.Point()
			ptGeoms = []
			for p in placeList:
				pt.X = float(p[4])
				pt.Y = float(p[3])
				pointGeometry = arcpy.PointGeometry(pt, spatial_reference)
				ptGeoms.append(pointGeometry)

			# out_path = pythonaddins.SaveDialog("Save Nearby Places", "placeNear",
			#                                    os.path.dirname(arcpy.mapping.MapDocument("current").filePath),
			#                                    FileGDBSave())

			if out_path == None:
				messages.addMessage("No data will be added to the map document.")
				# pythonaddins.MessageBox("No data will be added to the map document.", "Warning Message", 0)
			else:
				# create a geometry Feature class to represent 
				placeNearFeatureClass = arcpy.CopyFeatures_management(ptGeoms, out_path)

				labelFieldLength = Json2Field.fieldLengthDecide(bufferQueryResult, "placeLabel")
				arcpy.AddMessage("labelFieldLength: {0}".format(labelFieldLength))
				# add field to this point feature class
				arcpy.AddField_management(placeNearFeatureClass, "Label", "TEXT", field_length=labelFieldLength)
				arcpy.AddField_management(placeNearFeatureClass, "URL", "TEXT", field_length=100)
				# arcpy.AddField_management(placeNearFeatureClass, "TypeURL", "TEXT", field_length=50)
				# arcpy.AddField_management(placeNearFeatureClass, "TypeName", "TEXT", field_length=50)
				# if selectedURL != None:
				# 	arcpy.AddField_management(placeNearFeatureClass, "BTypeURL", "TEXT", field_length=50)
				# 	arcpy.AddField_management(placeNearFeatureClass, "BTypeName", "TEXT", field_length=50)
				# arcpy.AddField_management(placeNearFeatureClass, "Latitude", "TEXT", 10, 10)
				# arcpy.AddField_management(placeNearFeatureClass, "Longitude", "TEXT", 10, 10)

				arcpy.AddXY_management(placeNearFeatureClass)
				# add label, latitude, longitude value to this point feature class

				i = 0
				cursor = arcpy.UpdateCursor(out_path)
				row = cursor.next()
				while row:
					row.setValue("Label", placeList[i][1])
					row.setValue("URL", placeList[i][0])
					# row.setValue("TypeURL", placeList[i][5])
					# row.setValue("TypeName", placeList[i][6])
					cursor.updateRow(row)
					i = i + 1
					row = cursor.next()

				# if selectedURL != None:
				# 	i = 0
				# 	cursor = arcpy.UpdateCursor(out_path)
				# 	row = cursor.next()
				# 	while row:
				# 		row.setValue("BTypeURL", selectedURL)
				# 		row.setValue("BTypeName", inPlaceType)
				# 		cursor.updateRow(row)
				# 		i = i + 1
				# 		row = cursor.next()

				# get the map document
				# mxd = arcpy.mapping.MapDocument(
				#     r"D:\UCSB_STKO_Lab\STKO Research\research\DBpedia-Search-plugin\wiki1.mxd")



				mxd = arcpy.mapping.MapDocument("CURRENT")

				# get the data frame
				df = arcpy.mapping.ListDataFrames(mxd)[0]

				# create a new layer
				placeNearLayer = arcpy.mapping.Layer(out_path)

				# add the layer to the map at the bottom of the TOC in data frame 0
				arcpy.mapping.AddLayer(df, placeNearLayer, "BOTTOM")

		return



class LinkedDataPropertyEnrich(object):
	count = 0
	propertyNameList = []
	propertyURLList = []
	propertyURLDict = dict()

	inversePropertyNameList = []
	inversePropertyURLList = []
	inversePropertyURLDict = dict()

	expandedPropertyNameList = []
	expandedPropertyURLList = []
	expandedPropertyURLDict = dict()

	inverseExpandedPropertyNameList = []
	inverseExpandedPropertyURLList = []
	inverseExpandedPropertyURLDict = dict()

	# FunctionalPropertySet = Set()
	# noFunctionalPropertyURLList = []
	# noFunctionalPropertyNameList = []
	# noFunctionalPropertyURLDict = dict()

	def __init__(self):
		"""Define the tool (tool name is the name of the class)."""
		self.label = "Linked Data Location Entities Property Enrichment"
		self.description = "Get the most common properties from DBpedia according to input wikidata location entity IRI"
		self.canRunInBackground = False
		# self.propertyURLList = []
		#propertyNameList = []
		LinkedDataPropertyEnrich.count += 1
		

	def getParameterInfo(self):
		"""Define parameter definitions"""
		# The input Feature class which is the output of LinkedDataAnalysis Tool, "URL" column should be included in the attribute table
		in_wikiplace_IRI = arcpy.Parameter(
			displayName="Input wikidata location entities Feature Class",
			name="in_wikiplace_IRI",
			datatype="DEFeatureClass",
			parameterType="Required",
			direction="Input")

		# Use __file__ attribute to find the .lyr file (assuming the
		#  .pyt and .lyr files exist in the same folder)
		in_wikiplace_IRI.filter.list = ["Point"]

		# Choose place type for search
		in_com_property = arcpy.Parameter(
			displayName="Common Properties",
			name="in_com_property",
			datatype="GPString",
			parameterType="Optional",
			direction="Input",
			multiValue=True)

		# in_com_property.parameterDependencies = [in_wikiplace_IRI.name]
		# in_com_property.columns =([["GPString", "GPString"], ["GPString","GPString"]])

		# in_com_property.filters[0].type = 'ValueList'
		# in_com_property.filters[0].list = []

		# in_com_property.filters[1].type = 'ValueList'
		# in_com_property.filters[1].list = []

		in_com_property.filter.type = "ValueList"
		in_com_property.filter.list = []

		in_boolean_inverse_com = arcpy.Parameter(
			displayName="Get Inverse Common Properties",
			name="in_boolean_inverse_com",
			datatype="GPBoolean",
			parameterType="Optional",
			direction="Input")

		in_boolean_inverse_com.value = False

		in_inverse_com_property = arcpy.Parameter(
			displayName="Inverse Common Properties",
			name="in_inverse_com_property",
			datatype="GPString",
			parameterType="Optional",
			direction="Input",
			multiValue=True)

		in_inverse_com_property.filter.type = "ValueList"
		in_inverse_com_property.filter.list = []
		in_inverse_com_property.enabled = False


		in_boolean_isPartOf = arcpy.Parameter(
			displayName="Get Expanded Common Properties by following Transitive Inverse Partonomical and Subdivision Paths",
			name="in_boolean_isPartOf",
			datatype="GPBoolean",
			parameterType="Optional",
			direction="Input")

		in_boolean_isPartOf.value = False
		
		in_expanded_com_property = arcpy.Parameter(
			displayName="Expanded Common Properties",
			name="in_expanded_com_property",
			datatype="GPString",
			parameterType="Optional",
			direction="Input",
			multiValue=True)

		in_expanded_com_property.filter.type = "ValueList"
		in_expanded_com_property.filter.list = []
		in_expanded_com_property.enabled = False

		in_boolean_inverse_expanded_com = arcpy.Parameter(
			displayName="Get Inverse Expanded Common Properties",
			name="in_boolean_inverse_expanded_com",
			datatype="GPBoolean",
			parameterType="Optional",
			direction="Input")

		in_boolean_inverse_expanded_com.value = False

		in_inverse_expanded_com_property = arcpy.Parameter(
			displayName="Inverse Expanded Common Properties",
			name="in_inverse_expanded_com_property",
			datatype="GPString",
			parameterType="Optional",
			direction="Input",
			multiValue=True)

		in_inverse_expanded_com_property.filter.type = "ValueList"
		in_inverse_expanded_com_property.filter.list = []
		in_inverse_expanded_com_property.enabled = False

		# out_location = arcpy.Parameter(
		# 	displayName="Output Location",
		# 	name="out_location",
		# 	datatype="DEWorkspace",
		# 	parameterType="Required",
		# 	direction="Input")

		# out_location.value = os.path.dirname(__file__)

		# # Derived Output Property Table Name
		# out_property_table_name = arcpy.Parameter(
		# 	displayName="Output Property Table Name",
		# 	name="out_property_table_name",
		# 	datatype="GPString",
		# 	parameterType="Required",
		# 	direction="Input")


		# # Save the select property URL
		# out_com_property_URL = arcpy.Parameter(
		# 	displayName="Common Property",
		# 	name="out_com_property_URL",
		# 	datatype="GPString",
		# 	parameterType="Derived",
		# 	direction="Output",
		# 	multiValue=True)

		# out_com_property_URL.filter.type = "ValueList"
		# out_com_property_URL.filter.list = []

		

		# params = [in_wikiplace_IRI, in_com_property, out_location, out_property_table_name, out_com_property_URL]
		params = [in_wikiplace_IRI, in_com_property, in_boolean_inverse_com, in_inverse_com_property, in_boolean_isPartOf, in_expanded_com_property, in_boolean_inverse_expanded_com, in_inverse_expanded_com_property]

		return params



	def isLicensed(self):
		"""Set whether tool is licensed to execute."""
		return True

	def updateParameters(self, parameters):
		"""Modify the values and properties of parameters before internal
		validation is performed.  This method is called whenever a parameter
		has been changed."""
		in_wikiplace_IRI = parameters[0]
		in_com_property = parameters[1]
		in_boolean_inverse_com = parameters[2]
		in_inverse_com_property = parameters[3]
		in_boolean_isPartOf = parameters[4]
		in_expanded_com_property = parameters[5]
		in_boolean_inverse_expanded_com = parameters[6]
		in_inverse_expanded_com_property = parameters[7]
		# out_location = parameters[2]
		# out_property_table_name = parameters[3]
		# out_com_property_URL = parameters[4]

		isInverse = False

		if in_boolean_inverse_com.valueAsText == 'true':
			isInverse = True
		elif in_boolean_inverse_com.valueAsText == 'false':
			isInverse = False


		isExpandedPartOf = False
		
		if in_boolean_isPartOf.valueAsText == 'true':
			isExpandedPartOf = True
		elif in_boolean_isPartOf.valueAsText == 'false':
			isExpandedPartOf = False

		isInverseExpanded = False

		if in_boolean_inverse_expanded_com.valueAsText == 'true':
			isInverseExpanded = True
		elif in_boolean_inverse_expanded_com.valueAsText == 'false':
			isInverseExpanded = False

		arcpy.AddMessage(("in_boolean_isPartOf.valueAsText: {0}").format(in_boolean_isPartOf.valueAsText))

		if isInverse == False:
			in_inverse_com_property.enabled = False
		else:
			in_inverse_com_property.enabled = True


		if isExpandedPartOf == False:
			in_expanded_com_property.enabled = False
			in_inverse_expanded_com_property.enabled = False
		else:
			in_expanded_com_property.enabled = True
			if isInverseExpanded == False:
				in_inverse_expanded_com_property.enabled = False
			else:
				in_inverse_expanded_com_property.enabled = True

		if in_wikiplace_IRI.value:
			inputFeatureClassName = in_wikiplace_IRI.valueAsText
			arcpy.AddMessage("{0}".format(inputFeatureClassName))
			# inputFeatureClass = arcpy.Describe(inputFeatureClassName)
			fieldList = arcpy.ListFields(inputFeatureClassName)
			isURLinFieldList = False
			for field in fieldList:
				if field.name == "URL":
					isURLinFieldList = True

			if isURLinFieldList == False:
				arcpy.AddErrorMessage("Please a point feature class which include a 'URL' Field for the wikidata IRI of this entity")
				raise arcpy.ExecuteError
			else:
				# update the output directory of this tool to the same geodatabase 
				lastIndexOFGDB = inputFeatureClassName.rfind("\\")
				outputLocation = inputFeatureClassName[:lastIndexOFGDB]
				# out_location.value = outputLocation

				# get all the IRI from input point feature class of wikidata places
				inplaceIRIList = []
				cursor = arcpy.SearchCursor(inputFeatureClassName)
				for row in cursor:
					inplaceIRIList.append(row.getValue("URL"))

				if len(inplaceIRIList) == 0:
					arcpy.AddMessage("Input Feature class do not have record")
					raise arcpy.ExecuteError
				else:
					# get the direct common property 
					commonPropertyJSONObj = SPARQLQuery.commonPropertyQuery(inplaceIRIList)
					commonPropertyJSON = commonPropertyJSONObj["results"]["bindings"]

					if len(commonPropertyJSON) == 0:
						arcpy.AddMessage("No property find.")
						raise arcpy.ExecuteError
					else:
						LinkedDataPropertyEnrich.propertyURLList = []
						LinkedDataPropertyEnrich.propertyNameList = []
						LinkedDataPropertyEnrich.propertyURLDict = dict()
						# LinkedDataPropertyEnrich.FunctionalPropertySet = Set()
						# LinkedDataPropertyEnrich.noFunctionalPropertyURLList = []
						# LinkedDataPropertyEnrich.noFunctionalPropertyNameList = []
						# LinkedDataPropertyEnrich.noFunctionalPropertyURLDict = dict()

						for jsonItem in commonPropertyJSON:
							propertyURL = jsonItem["p"]["value"]
							if "http://dbpedia.org/ontology/" in propertyURL or "http://dbpedia.org/property/" in propertyURL:
								if propertyURL not in LinkedDataPropertyEnrich.propertyURLList:
									LinkedDataPropertyEnrich.propertyURLList.append(propertyURL)
									lastIndex = propertyURL.rfind("/")
									propertyName = propertyURL[(lastIndex+1):]
									if "http://dbpedia.org/ontology/" in propertyURL:
										lastIndex = len("http://dbpedia.org/ontology/")
										propertyName = propertyURL[lastIndex:]
										propertyName = "dbo:" + propertyName + "(" + jsonItem["NumofSub"]["value"] +  ")"
									elif "http://dbpedia.org/property/" in propertyURL:
										lastIndex = len("http://dbpedia.org/property/")
										propertyName = propertyURL[lastIndex:]
										propertyName = "dbp:" + propertyName + "(" + jsonItem["NumofSub"]["value"] +  ")"
									# propertyName = propertyName + "(" + jsonItem["NumofSub"]["value"] +  ")"
									LinkedDataPropertyEnrich.propertyNameList.append(propertyName)
								# propertyNameURLList.append(propertyURL + "     " +propertyName)
						LinkedDataPropertyEnrich.propertyURLDict = dict(zip(LinkedDataPropertyEnrich.propertyNameList, LinkedDataPropertyEnrich.propertyURLList))

						in_com_property.filter.list = LinkedDataPropertyEnrich.propertyNameList
						# in_com_property.filters[0] = LinkedDataPropertyEnrich.propertyNameList
						# in_com_property.filter.list = LinkedDataPropertyEnrich.propertyNameList
						# in_com_property.filters[0].list = LinkedDataPropertyEnrich.propertyNameList
						# in_com_property.filters[1].list = LinkedDataPropertyEnrich.propertyURLList
						# arcpy.AddMessage("URLLIst: {0}".format(LinkedDataPropertyEnrich.propertyURLList))
						# arcpy.AddMessage("NameLIst: {0}".format(LinkedDataPropertyEnrich.propertyNameList))
						# out_com_property_URL.filter.list = LinkedDataPropertyEnrich.propertyURLList

					# get the inverse direct common property 
					if isInverse == True:
						inverseCommonPropertyJSONObj = SPARQLQuery.inverseCommonPropertyQuery(inplaceIRIList)
						inverseCommonPropertyJSON = inverseCommonPropertyJSONObj["results"]["bindings"]

						if len(inverseCommonPropertyJSON) == 0:
							arcpy.AddMessage("No inverse property find.")
							raise arcpy.ExecuteError
						else:
							LinkedDataPropertyEnrich.inversePropertyNameList = []
							LinkedDataPropertyEnrich.inversePropertyURLList = []
							LinkedDataPropertyEnrich.inversePropertyURLDict = dict()
							# LinkedDataPropertyEnrich.propertyURLList = []
							# LinkedDataPropertyEnrich.propertyNameList = []
							# LinkedDataPropertyEnrich.propertyURLDict = dict()
							

							for jsonItem in inverseCommonPropertyJSON:
								propertyURL = jsonItem["p"]["value"]
								if "http://dbpedia.org/ontology/" in propertyURL or "http://dbpedia.org/property/" in propertyURL:
									if propertyURL not in LinkedDataPropertyEnrich.inversePropertyURLList:
										LinkedDataPropertyEnrich.inversePropertyURLList.append(propertyURL)
										# lastIndex = propertyURL.rfind("/")
										# propertyName = propertyURL[(lastIndex+1):]
										if "http://dbpedia.org/ontology/" in propertyURL:
											lastIndex = len("http://dbpedia.org/ontology/")
											propertyName = propertyURL[lastIndex:]
											propertyName = "is dbo:" + propertyName + " Of (" + jsonItem["NumofSub"]["value"] +  ")"
										elif "http://dbpedia.org/property/" in propertyURL:
											lastIndex = len("http://dbpedia.org/property/")
											propertyName = propertyURL[lastIndex:]
											propertyName = "is dbp:" + propertyName + " Of (" + jsonItem["NumofSub"]["value"] +  ")"
										# propertyName = propertyName + "(" + jsonItem["NumofSub"]["value"] +  ")"
										LinkedDataPropertyEnrich.inversePropertyNameList.append(propertyName)
									# propertyNameURLList.append(propertyURL + "     " +propertyName)
							LinkedDataPropertyEnrich.inversePropertyURLDict = dict(zip(LinkedDataPropertyEnrich.inversePropertyNameList, LinkedDataPropertyEnrich.inversePropertyURLList))

							in_inverse_com_property.filter.list = LinkedDataPropertyEnrich.inversePropertyNameList

					if isExpandedPartOf == True:
						expandedCommonPropertyJSONObj = SPARQLQuery.locationDBpediaExpandedCommonPropertyQuery(inplaceIRIList)
						expandedCommonPropertyJSON = expandedCommonPropertyJSONObj["results"]["bindings"]

						if len(expandedCommonPropertyJSON) == 0:
							arcpy.AddMessage("No expanded property find.")
							raise arcpy.ExecuteError
						else:
							# LinkedDataPropertyEnrich.propertyURLList = []
							# LinkedDataPropertyEnrich.propertyNameList = []
							# LinkedDataPropertyEnrich.propertyURLDict = dict()
							# LinkedDataPropertyEnrich.FunctionalPropertySet = Set()
							LinkedDataPropertyEnrich.expandedPropertyNameList = []
							LinkedDataPropertyEnrich.expandedPropertyURLList = []
							LinkedDataPropertyEnrich.expandedPropertyURLDict = dict()

							for jsonItem in expandedCommonPropertyJSON:
								propertyURL = jsonItem["p"]["value"]
								if "http://dbpedia.org/ontology/" in propertyURL or "http://dbpedia.org/property/" in propertyURL:
									if propertyURL not in LinkedDataPropertyEnrich.expandedPropertyURLList:
										LinkedDataPropertyEnrich.expandedPropertyURLList.append(propertyURL)
										# lastIndex = propertyURL.rfind("/")
										# propertyName = propertyURL[(lastIndex+1):]
										if "http://dbpedia.org/ontology/" in propertyURL:
											lastIndex = len("http://dbpedia.org/ontology/")
											propertyName = propertyURL[lastIndex:]
											propertyName = "dbo:" + propertyName + "(" + jsonItem["NumofSub"]["value"] +  ")"
										elif "http://dbpedia.org/property/" in propertyURL:
											lastIndex = len("http://dbpedia.org/property/")
											propertyName = propertyURL[lastIndex:]
											propertyName = "dbp:" + propertyName + "(" + jsonItem["NumofSub"]["value"] +  ")"
										# propertyName = propertyName + "(" + jsonItem["NumofSub"]["value"] +  ")"
										LinkedDataPropertyEnrich.expandedPropertyNameList.append(propertyName)
									# propertyNameURLList.append(propertyURL + "     " +propertyName)
							LinkedDataPropertyEnrich.expandedPropertyURLDict = dict(zip(LinkedDataPropertyEnrich.expandedPropertyNameList, LinkedDataPropertyEnrich.expandedPropertyURLList))

							in_expanded_com_property.filter.list = LinkedDataPropertyEnrich.expandedPropertyNameList


						if isInverseExpanded == True:
							inverseExpandedCommonPropertyJSONObj = SPARQLQuery.locationDBpediaInverseExpandedCommonPropertyQuery(inplaceIRIList)
							inverseExpandedCommonPropertyJSON = inverseExpandedCommonPropertyJSONObj["results"]["bindings"]

							if len(inverseExpandedCommonPropertyJSON) == 0:
								arcpy.AddMessage("No inverse expanded property find.")
								raise arcpy.ExecuteError
							else:
								# LinkedDataPropertyEnrich.propertyURLList = []
								# LinkedDataPropertyEnrich.propertyNameList = []
								# LinkedDataPropertyEnrich.propertyURLDict = dict()
								# LinkedDataPropertyEnrich.FunctionalPropertySet = Set()
								LinkedDataPropertyEnrich.inverseExpandedPropertyNameList = []
								LinkedDataPropertyEnrich.inverseExpandedPropertyURLList = []
								LinkedDataPropertyEnrich.inverseExpandedPropertyURLDict = dict()

								for jsonItem in inverseExpandedCommonPropertyJSON:
									propertyURL = jsonItem["p"]["value"]
									if "http://dbpedia.org/ontology/" in propertyURL or "http://dbpedia.org/property/" in propertyURL:
										if propertyURL not in LinkedDataPropertyEnrich.inverseExpandedPropertyURLList:
											LinkedDataPropertyEnrich.inverseExpandedPropertyURLList.append(propertyURL)
											
											if "http://dbpedia.org/ontology/" in propertyURL:
												lastIndex = len("http://dbpedia.org/ontology/")
												propertyName = propertyURL[lastIndex:]
												propertyName = "is dbo:" + propertyName + " Of (" + jsonItem["NumofSub"]["value"] +  ")"
											elif "http://dbpedia.org/property/" in propertyURL:
												lastIndex = len("http://dbpedia.org/property/")
												propertyName = propertyURL[lastIndex:]
												propertyName = "is dbp:" + propertyName + " Of (" + jsonItem["NumofSub"]["value"] +  ")"
											# propertyName = propertyName + "(" + jsonItem["NumofSub"]["value"] +  ")"
											LinkedDataPropertyEnrich.inverseExpandedPropertyNameList.append(propertyName)
										# propertyNameURLList.append(propertyURL + "     " +propertyName)
								LinkedDataPropertyEnrich.inverseExpandedPropertyURLDict = dict(zip(LinkedDataPropertyEnrich.inverseExpandedPropertyNameList, LinkedDataPropertyEnrich.inverseExpandedPropertyURLList))

								in_inverse_expanded_com_property.filter.list = LinkedDataPropertyEnrich.inverseExpandedPropertyNameList


						# # send a SPARQL query to DBpedia endpoint to test whether the properties are functionalProperty
						# isFuncnalPropertyJSONObj = SPARQLQuery.functionalPropertyQuery(LinkedDataPropertyEnrich.propertyURLList)
						# isFuncnalPropertyJSON = isFuncnalPropertyJSONObj["results"]["bindings"]

						# FunctionalPropertySet = Set()
			
						# for jsonItem in isFuncnalPropertyJSON:
						# 	functionalPropertyURL = jsonItem["property"]["value"]
						# 	FunctionalPropertySet.add(functionalPropertyURL)

						# LinkedDataPropertyEnrich.FunctionalPropertySet = FunctionalPropertySet


						# use set differences to get the no functional property set 
						# propertyURLSet = Set(LinkedDataPropertyEnrich.propertyURLList)
						# noFunctionalPropertySet = propertyURLSet.difference(FunctionalPropertySet)
						# LinkedDataPropertyEnrich.noFunctionalPropertyURLList = list(noFunctionalPropertySet)

						# for propertyURL in LinkedDataPropertyEnrich.noFunctionalPropertyURLList:
						# 	if "http://dbpedia.org/ontology/" in propertyURL:
						# 		lastIndex = len("http://dbpedia.org/ontology/")
						# 		propertyName = propertyURL[lastIndex:]
						# 		propertyName = "dbo:" + propertyName
						# 	elif "http://dbpedia.org/property/" in propertyURL:
						# 		lastIndex = len("http://dbpedia.org/property/")
						# 		propertyName = propertyURL[lastIndex:]
						# 		propertyName = "dbp:" + propertyName

						# 	LinkedDataPropertyEnrich.noFunctionalPropertyNameList.append(propertyName)

						# LinkedDataPropertyEnrich.noFunctionalPropertyURLDict = dict(zip(LinkedDataPropertyEnrich.noFunctionalPropertyNameList, LinkedDataPropertyEnrich.noFunctionalPropertyURLList))


		return

	def updateMessages(self, parameters):
		"""Modify the messages created by internal validation for each tool
		parameter.  This method is called after internal validation."""
		return

	def execute(self, parameters, messages):
		"""The source code of the tool."""
		in_wikiplace_IRI = parameters[0]
		in_com_property = parameters[1]
		in_boolean_inverse_com = parameters[2]
		in_inverse_com_property = parameters[3]
		in_boolean_isPartOf = parameters[4]
		in_expanded_com_property = parameters[5]
		in_boolean_inverse_expanded_com = parameters[6]
		in_inverse_expanded_com_property = parameters[7]
		# out_location = parameters[2]
		# out_property_table_name = parameters[3]
		# out_com_property_URL = parameters[4]
		
		# arcpy.AddMessage("propertyNameList: {0}".format(LinkedDataPropertyEnrich.propertyNameList))
		# arcpy.AddMessage("propertyURLList: {0}".format(LinkedDataPropertyEnrich.propertyURLList))
		isInverse = False

		if in_boolean_inverse_com.valueAsText == 'true':
			isInverse = True
		elif in_boolean_inverse_com.valueAsText == 'false':
			isInverse = False


		isExpandedPartOf = False
		
		if in_boolean_isPartOf.valueAsText == 'true':
			isExpandedPartOf = True
		elif in_boolean_isPartOf.valueAsText == 'false':
			isExpandedPartOf = False

		isInverseExpanded = False

		if in_boolean_inverse_expanded_com.valueAsText == 'true':
			isInverseExpanded = True
		elif in_boolean_inverse_expanded_com.valueAsText == 'false':
			isInverseExpanded = False

		

		arcpy.AddMessage(("in_boolean_isPartOf.valueAsText: {0}").format(in_boolean_isPartOf.valueAsText))

		for URL in LinkedDataPropertyEnrich.propertyURLList:
			arcpy.AddMessage(URL)

		arcpy.AddMessage("count: {0}".format(LinkedDataPropertyEnrich.count))

		# arcpy.AddMessage("FunctionalPropertySet: {0}".format(LinkedDataPropertyEnrich.FunctionalPropertySet))
		
		inputFeatureClassName = in_wikiplace_IRI.valueAsText
		lastIndexOFGDB = inputFeatureClassName.rfind("\\")
		outputLocation = inputFeatureClassName[:lastIndexOFGDB]

		if outputLocation.endswith(".gdb") == False:
			messages.addErrorMessage("Please enter a feature class in file geodatabase for the input feature class in order to create a relation class")
			raise arcpy.ExecuteError
		else:
			arcpy.env.workspace = outputLocation

			lastIndexOFFeatureClassName = inputFeatureClassName.rfind("\\")
			featureClassName = inputFeatureClassName[(lastIndexOFGDB+1):]

			# get all the IRI from input point feature class of wikidata places
			inplaceIRIList = []
			cursor = arcpy.SearchCursor(inputFeatureClassName)
			for row in cursor:
				inplaceIRIList.append(row.getValue("URL"))

			# send a SPARQL query to DBpedia endpoint to get the DBpedia IRI according to wikidata IRI
			dbpediaIRIJSONObj = SPARQLQuery.dbpediaIRIQuery(inplaceIRIList)
			dbpediaIRIJSON = dbpediaIRIJSONObj["results"]["bindings"]
			
			# according to dbpediaIRIJSON, add or update the field "DBpediaURL" in inputFeatureClass table
			Json2Field.addOrUpdateFieldInTableByMapping(dbpediaIRIJSON, "wikidataSub", "DBpediaSub", inputFeatureClassName, "URL", "DBpediaURL")

			# if outputLocation != out_location.valueAsText:
			# 	messages.addErrorMessage("Please make the output location the same geodatabase as the input Feature class")
			# 	raise arcpy.ExecuteError
			# else:
			arcpy.AddMessage(in_com_property.valueAsText)
			propertySelect = in_com_property.valueAsText
			selectPropertyURLList = []
			if propertySelect != None:

				propertySplitList = re.split("[;]", propertySelect)
				for propertyItem in propertySplitList:
					# lastIndex = propertyItem.rfind("(")
					# propertyItem = propertyItem[:lastIndex]
					selectPropertyURLList.append(LinkedDataPropertyEnrich.propertyURLDict[propertyItem])
					# propertyURL = "http://dbpedia.org/ontology/" + propertyItem[:lastIndex]
					# LinkedDataPropertyEnrich.propertyURLList.append(propertyURL)


				# arcpy.AddMessage("URLList: {0}".format(LinkedDataPropertyEnrich.propertyURLList))

				# # send a SPARQL query to DBpedia endpoint to test whether the user selected properties are functionalProperty
				# isFuncnalPropertyALLJSONObj = SPARQLQuery.functionalPropertyQuery(LinkedDataPropertyEnrich.propertyURLList)
				# isFuncnalPropertyALLJSON = isFuncnalPropertyALLJSONObj["results"]["bindings"]
				

				# send a SPARQL query to DBpedia endpoint to test whether the user selected properties are functionalProperty
				# isFuncnalPropertyJSONObj = SPARQLQuery.functionalPropertyQuery(selectPropertyURLList)
				# isFuncnalPropertyJSON = isFuncnalPropertyJSONObj["results"]["bindings"]

				# FuncnalPropertySet = Set()
				
				# for jsonItem in isFuncnalPropertyJSON:
				# 	functionalPropertyURL = jsonItem["property"]["value"]
				# 	FuncnalPropertySet.add(functionalPropertyURL)

				# send a SPARQL query to DBpedia endpoint to test whether the properties are functionalProperty
				isFuncnalPropertyJSON = SPARQLQuery.functionalPropertyQuery(selectPropertyURLList)
				# isFuncnalPropertyJSON = isFuncnalPropertyJSONObj["results"]["bindings"]

				FunctionalPropertySet = Set()

				for jsonItem in isFuncnalPropertyJSON:
					functionalPropertyURL = jsonItem["property"]["value"]
					FunctionalPropertySet.add(functionalPropertyURL)

				# LinkedDataPropertyEnrich.FunctionalPropertySet = FunctionalPropertySet

				# # the selected functional properties
				# functionalPropertySet = Set()

				# FuncnalPropertySet = Set()
				# for propertyURL in selectPropertyURLList:
				# 	if propertyURL in LinkedDataPropertyEnrich.FunctionalPropertySet:
				# 		functionalPropertySet.add(propertyURL)


				arcpy.AddMessage("FunctionalPropertySet: {0}".format(FunctionalPropertySet))

				# get the value for each functionalProperty
				FuncnalPropertyList = list(FunctionalPropertySet)
				# add these functionalProperty value to feature class table
				for functionalProperty in FuncnalPropertyList:
					functionalPropertyJSON = SPARQLQuery.propertyValueQuery(inplaceIRIList, functionalProperty)
					# functionalPropertyJSON = functionalPropertyJSONObj["results"]["bindings"]

					Json2Field.addFieldInTableByMapping(functionalPropertyJSON, "wikidataSub", "o", inputFeatureClassName, "URL", functionalProperty, False)
					
				selectPropertyURLSet = Set(selectPropertyURLList)
				noFunctionalPropertySet = selectPropertyURLSet.difference(FunctionalPropertySet)
				noFunctionalPropertyList = list(noFunctionalPropertySet)

				for noFunctionalProperty in noFunctionalPropertyList:
					noFunctionalPropertyJSON = SPARQLQuery.propertyValueQuery(inplaceIRIList, noFunctionalProperty)
					# noFunctionalPropertyJSON = noFunctionalPropertyJSONObj["results"]["bindings"]
					# create a seperate table to store one-to-many property value, return the created table name
					tableName = Json2Field.createMappingTableFromJSON(noFunctionalPropertyJSON, "wikidataSub", "o", noFunctionalProperty, inputFeatureClassName, "wikiURL", False, False)
					# creat relationship class between the original feature class and the created table
					
					relationshipClassName = featureClassName + "_" + tableName + "_RelClass"
					arcpy.CreateRelationshipClass_management(featureClassName, tableName, relationshipClassName, "SIMPLE",
						noFunctionalProperty, "features from wikidata",
										 "FORWARD", "ONE_TO_MANY", "NONE", "URL", "wikiURL")

			# if the user want the inverse properties
			if isInverse == True:
				inversePropertySelect = in_inverse_com_property.valueAsText
				arcpy.AddMessage("LinkedDataPropertyEnrich.inversePropertyURLDict: {0}".format(LinkedDataPropertyEnrich.inversePropertyURLDict))
				arcpy.AddMessage("inversePropertySelect: {0}".format(inversePropertySelect))

				selectInversePropertyURLList = []
				inversePropertySplitList = re.split("[;]", inversePropertySelect)
				for propertyItem in inversePropertySplitList:
					
					selectInversePropertyURLList.append(LinkedDataPropertyEnrich.inversePropertyURLDict[propertyItem.split("\'")[1]])
					

				# send a SPARQL query to DBpedia endpoint to test whether the properties are InverseFunctionalProperty
				isInverseFuncnalPropertyJSON = SPARQLQuery.inverseFunctionalPropertyQuery(selectInversePropertyURLList)
				# isFuncnalPropertyJSON = isFuncnalPropertyJSONObj["results"]["bindings"]

				inverseFunctionalPropertySet = Set()

				for jsonItem in isInverseFuncnalPropertyJSON:
					inverseFunctionalPropertyURL = jsonItem["property"]["value"]
					inverseFunctionalPropertySet.add(inverseFunctionalPropertyURL)

				arcpy.AddMessage("inverseFunctionalPropertySet: {0}".format(inverseFunctionalPropertySet))

				# get the value for each functionalProperty
				inverseFuncnalPropertyList = list(inverseFunctionalPropertySet)
				# add these inverseFunctionalProperty subject value to feature class table
				for inverseFunctionalProperty in inverseFuncnalPropertyList:
					inverseFunctionalPropertyJSON = SPARQLQuery.inversePropertyValueQuery(inplaceIRIList, inverseFunctionalProperty)
					# functionalPropertyJSON = functionalPropertyJSONObj["results"]["bindings"]

					Json2Field.addFieldInTableByMapping(inverseFunctionalPropertyJSON, "wikidataSub", "o", inputFeatureClassName, "URL", inverseFunctionalProperty, True)
					
				selectInversePropertyURLSet = Set(selectInversePropertyURLList)
				noFunctionalInversePropertySet = selectInversePropertyURLSet.difference(inverseFunctionalPropertySet)
				noFunctionalInversePropertyList = list(noFunctionalInversePropertySet)

				for noFunctionalInverseProperty in noFunctionalInversePropertyList:
					noFunctionalInversePropertyJSON = SPARQLQuery.inversePropertyValueQuery(inplaceIRIList, noFunctionalInverseProperty)
					# noFunctionalPropertyJSON = noFunctionalPropertyJSONObj["results"]["bindings"]
					# create a seperate table to store one-to-many property-subject pair, return the created table name
					tableName = Json2Field.createMappingTableFromJSON(noFunctionalInversePropertyJSON, "wikidataSub", "o", noFunctionalInverseProperty, inputFeatureClassName, "wikiURL", True, False)
					# creat relationship class between the original feature class and the created table
					
					relationshipClassName = featureClassName + "_" + tableName + "_RelClass"
					arcpy.AddMessage("featureClassName: {0}".format(featureClassName))
					arcpy.AddMessage("tableName: {0}".format(tableName))
					arcpy.CreateRelationshipClass_management(featureClassName, tableName, relationshipClassName, "SIMPLE",
						noFunctionalInverseProperty, "features from wikidata",
										 "FORWARD", "ONE_TO_MANY", "NONE", "URL", "wikiURL")

			# if the user want the expanded properties
			if isExpandedPartOf == True:
				arcpy.AddMessage(in_expanded_com_property.valueAsText)
				expandedPropertySelect = in_expanded_com_property.valueAsText
				selectExpandedPropertyURLList = []
				expandedPropertySplitList = re.split("[;]", expandedPropertySelect)
				for propertyItem in expandedPropertySplitList:
					selectExpandedPropertyURLList.append(LinkedDataPropertyEnrich.expandedPropertyURLDict[propertyItem])


				isPartOfReverseTransiveJSON = SPARQLQuery.isPartOfReverseTransiveQuery(inplaceIRIList)
				# create a seperate table to store "isPartOf" transitive relationship, return the created table name
				isPartOfTableName = Json2Field.createMappingTableFromJSON(isPartOfReverseTransiveJSON, "wikidataSub", "subDivision", "http://dbpedia.org/ontology/isPartOf_reverse_Transtive", inputFeatureClassName, "wikiURL", False, True)
				# creat relationship class between the original feature class and the created table
				isPartOfRelationshipClassName = featureClassName + "_" + isPartOfTableName + "_RelClass"
				arcpy.CreateRelationshipClass_management(featureClassName, isPartOfTableName, isPartOfRelationshipClassName, "SIMPLE",
					"is \"http://dbpedia.org/ontology/isPartOf+\" of", "http://dbpedia.org/ontology/isPartOf+",
									 "FORWARD", "ONE_TO_MANY", "NONE", "URL", "wikiURL")

				# send a SPARQL query to DBpedia endpoint to test whether the properties are functionalProperty
				isFuncnalExpandedPropertyJSON = SPARQLQuery.functionalPropertyQuery(selectExpandedPropertyURLList)
				# isFuncnalPropertyJSON = isFuncnalPropertyJSONObj["results"]["bindings"]

				FunctionalExpandedPropertySet = Set()

				for jsonItem in isFuncnalExpandedPropertyJSON:
					functionalPropertyURL = jsonItem["property"]["value"]
					FunctionalExpandedPropertySet.add(functionalPropertyURL)


				# get the value for each functionalProperty
				FuncnalExpandedPropertyList = list(FunctionalExpandedPropertySet)
				# add these functionalProperty value to feature class table
				for functionalProperty in FuncnalExpandedPropertyList:
					functionalPropertyJSON = SPARQLQuery.expandedPropertyValueQuery(inplaceIRIList, functionalProperty)

					Json2Field.addFieldInTableByMapping(functionalPropertyJSON, "subDivision", "o", os.path.join(outputLocation, isPartOfTableName), "subDivisionIRI", functionalProperty, False)
					# Json2Field.addFieldInMultiKeyTableByMapping(jsonBindingObject, keyPropertyNameList, valuePropertyName, inputFeatureClassName, keyPropertyFieldNameList, valuePropertyURL, isInverse)
				selectExpandedPropertyURLSet = Set(selectExpandedPropertyURLList)
				noFunctionalExpandedPropertySet = selectExpandedPropertyURLSet.difference(FunctionalExpandedPropertySet)
				noFunctionalExpandedPropertyList = list(noFunctionalExpandedPropertySet)


				# SPARQLQuery.expandedPropertyValueQuery(inplaceIRIList, propertyURL) select ?wikidataSub ?subDivision ?o
				# createMappingTableFromJSON(jsonBindingObject, keyPropertyName, valuePropertyName, valuePropertyURL, inputFeatureClassName, keyPropertyFieldName)
				for propertyURL in noFunctionalExpandedPropertyList:
					expandedPropertyValueJSON = SPARQLQuery.expandedPropertyValueQuery(inplaceIRIList, propertyURL)
					# create a seperate table to store the value of the property of the subDivision got from "isPartOf" transitive relationship, return the created table name
					subDivisionValueTableName = Json2Field.createMappingTableFromJSON(expandedPropertyValueJSON, "subDivision", "o", propertyURL, os.path.join(outputLocation, isPartOfTableName), "DBpediaIRI", False, False)
					# creat relationship class between the isPartOfTableName and the created table
					subDivisionValueRelationshipClassName = isPartOfTableName + "_" + subDivisionValueTableName + "_RelClass"
					arcpy.CreateRelationshipClass_management(os.path.join(outputLocation, isPartOfTableName), subDivisionValueTableName, subDivisionValueRelationshipClassName, "SIMPLE",
						propertyURL, "Super Division of DBpediaIRI following \"isPartOf+\"",
										 "FORWARD", "ONE_TO_MANY", "NONE", "subDivisionIRI", "DBpediaIRI")

				if isInverseExpanded == True:
					arcpy.AddMessage(in_inverse_expanded_com_property.valueAsText)
					inverseExpandedPropertySelect = in_inverse_expanded_com_property.valueAsText
					selectInverseExpandedPropertyURLList = []
					inverseExpandedPropertySplitList = re.split("[;]", inverseExpandedPropertySelect)
					for propertyItem in inverseExpandedPropertySplitList:
						selectInverseExpandedPropertyURLList.append(LinkedDataPropertyEnrich.inverseExpandedPropertyURLDict[propertyItem.split("\'")[1]])

					# send a SPARQL query to DBpedia endpoint to test whether the properties are InverseFunctionalProperty
					isFuncnalInverseExpandedPropertyJSON = SPARQLQuery.inverseFunctionalPropertyQuery(selectInverseExpandedPropertyURLList)
					# isFuncnalPropertyJSON = isFuncnalPropertyJSONObj["results"]["bindings"]

					FunctionalInverseExpandedPropertySet = Set()

					for jsonItem in isFuncnalInverseExpandedPropertyJSON:
						inverseFunctionalPropertyURL = jsonItem["property"]["value"]
						FunctionalInverseExpandedPropertySet.add(inverseFunctionalPropertyURL)


					# get the value for each InverseFunctionalProperty
					FuncnalInverseExpandedPropertyList = list(FunctionalInverseExpandedPropertySet)
					# add these functionalProperty value to feature class table
					for inverseFunctionalProperty in FuncnalInverseExpandedPropertyList:
						inverseFunctionalPropertyJSON = SPARQLQuery.inverseExpandedPropertyValueQuery(inplaceIRIList, inverseFunctionalProperty)

						Json2Field.addFieldInTableByMapping(inverseFunctionalPropertyJSON, "subDivision", "o", os.path.join(outputLocation, isPartOfTableName), "subDivisionIRI", inverseFunctionalProperty, True)
						# Json2Field.addFieldInMultiKeyTableByMapping(jsonBindingObject, keyPropertyNameList, valuePropertyName, inputFeatureClassName, keyPropertyFieldNameList, valuePropertyURL, isInverse)
					selectInverseExpandedPropertyURLSet = Set(selectInverseExpandedPropertyURLList)
					noFunctionalInverseExpandedPropertySet = selectInverseExpandedPropertyURLSet.difference(FunctionalInverseExpandedPropertySet)
					noFunctionalInverseExpandedPropertyList = list(noFunctionalInverseExpandedPropertySet)

					for propertyURL in noFunctionalInverseExpandedPropertyList:
						inverseExpandedPropertyValueJSON = SPARQLQuery.inverseExpandedPropertyValueQuery(inplaceIRIList, propertyURL)
						# create a seperate table to store the value of the property of the subDivision got from "isPartOf" transitive relationship, return the created table name
						subDivisionValueTableName = Json2Field.createMappingTableFromJSON(inverseExpandedPropertyValueJSON, "subDivision", "o", propertyURL, os.path.join(outputLocation, isPartOfTableName), "DBpediaIRI", True, False)
						# creat relationship class between the isPartOfTableName and the created table
						subDivisionValueRelationshipClassName = isPartOfTableName + "_" + subDivisionValueTableName + "_RelClass"
						arcpy.CreateRelationshipClass_management(os.path.join(outputLocation, isPartOfTableName), subDivisionValueTableName, subDivisionValueRelationshipClassName, "SIMPLE",
							propertyURL, "Super Division of DBpediaIRI following \"isPartOf+\"",
											 "FORWARD", "ONE_TO_MANY", "NONE", "subDivisionIRI", "DBpediaIRI")

		return





class MergeBatchNoFunctionalProperty(object):
	relatedTableFieldList = []
	def __init__(self):
		"""Define the tool (tool name is the name of the class)."""
		self.label = "Linked Data Batch No Functional Property Merge"
		self.description = """The related seperated tables from Linked Data Location Entities Property Enrichment Tool have multivalue for each wikidata location because the coresponding property is not functional property. 
		This Tool helps user to merge these multivalue to a single record and add it to original feature class sttribute table by using merge rules which are specified by users."""
		self.canRunInBackground = False
		
	def getParameterInfo(self):
		"""Define parameter definitions"""
		# The input Feature class which is the output of LinkedDataAnalysis Tool, "URL" column should be included in the attribute table
		in_wikiplace_IRI = arcpy.Parameter(
			displayName="Input wikidata location entities Feature Class",
			name="in_wikiplace_IRI",
			datatype="DEFeatureClass",
			parameterType="Required",
			direction="Input")

		in_wikiplace_IRI.filter.list = ["Point"]

		# in_related_table = arcpy.Parameter(
		# 	displayName="Input no-functional property table which should be related to the input Feature Class",
		# 	name="in_related_table",
		# 	datatype="DETable",
		# 	parameterType="Required",
		# 	direction="Input")

		in_stat_fields = arcpy.Parameter(
		displayName='No functional Property Field(s) of related table of input feature class which need to Merge',
		name='in_stat_fields',
		datatype='GPValueTable',
		parameterType='Required',
		direction='Input')

		in_stat_fields.parameterDependencies = [in_wikiplace_IRI.name]
		in_stat_fields.columns = [['Field', 'Field'], ['GPString', 'Statistic Type'], ['DETable', 'Table Name']]
		in_stat_fields.filters[1].type = 'ValueList'
		# in_stat_fields.values = [['NAME', 'SUM']]
		in_stat_fields.filters[1].list = ['SUM', 'MIN', 'MAX', 'STDEV', 'MEAN', 'COUNT', 'FIRST', 'LAST']

		# out_location = arcpy.Parameter(
		# 	displayName="Output Location",
		# 	name="out_location",
		# 	datatype="DEWorkspace",
		# 	parameterType="Required",
		# 	direction="Input")

		# out_location.value = os.path.dirname(__file__)

		# # Derived Output Point Feature Class Name
		# out_points_name = arcpy.Parameter(
		# 	displayName="Output Point Feature Class Name with No-Functional Property Merged Values",
		# 	name="out_points_name",
		# 	datatype="GPString",
		# 	parameterType="Required",
		# 	direction="Input")

		# params = [in_wikiplace_IRI, in_stat_fields,out_location, out_points_name]
		params = [in_wikiplace_IRI, in_stat_fields]

		return params



	def isLicensed(self):
		"""Set whether tool is licensed to execute."""
		return True

	def updateParameters(self, parameters):
		"""Modify the values and properties of parameters before internal
		validation is performed.  This method is called whenever a parameter
		has been changed."""
		in_wikiplace_IRI = parameters[0]
		in_stat_fields = parameters[1]
		# out_location = parameters[2]
		# out_points_name = parameters[3]
		
		if in_wikiplace_IRI.altered and not in_stat_fields.altered:
			inputFeatureClassName = in_wikiplace_IRI.valueAsText
			lastIndexOFGDB = inputFeatureClassName.rfind("\\")
			featureClassName = inputFeatureClassName[(lastIndexOFGDB+1):]
			currentWorkspace = inputFeatureClassName[:lastIndexOFGDB]

			if currentWorkspace.endswith(".gdb") == False:
				messages.addErrorMessage("Please enter a feature class in file geodatabase for the input feature class.")
				raise arcpy.ExecuteError
			else:
				# if in_related_table.value:
				arcpy.env.workspace = currentWorkspace
				# out_location.value = currentWorkspace
				# out_points_name.value = featureClassName + "_noFunc_merge"
				# # check whether the input table are in the same file geodatabase as the input feature class
				# inputTableName = in_related_table.valueAsText
				# lastIndexOFTable = inputTableName.rfind("\\")
				# currentWorkspaceTable = inputTableName[:lastIndexOFTable]
				# if currentWorkspaceTable != currentWorkspace:
				# 	messages.addErrorMessage("Please enter a table in the same file geodatabase as the input feature class.")
				# 	raise arcpy.ExecuteError
				# else:
				# 	if UTIL.detectRelationship(inputFeatureClassName, inputTableName):
				# 		arcpy.AddMessage("The feature class and table are related!")
				relatedTableList = UTIL.getRelatedTableFromFeatureClass(inputFeatureClassName)
				# fieldmappings = arcpy.FieldMappings()
				# fieldmappings.addTable(inputFeatureClassName)
				
				noFunctionalPropertyTable = []

				for relatedTable in relatedTableList:
					fieldList = arcpy.ListFields(relatedTable)
					if "origin" not in fieldList and "end" not in fieldList:
						noFunctionalFieldName = fieldList[2].name
						arcpy.AddMessage("noFunctionalFieldName: {0}".format(noFunctionalFieldName))
						noFunctionalPropertyTable.append([noFunctionalFieldName, 'COUNT', relatedTable])
						# MergeNoFunctionalProperty.relatedTableFieldList.append([noFunctionalFieldName, relatedTable, 'COUNT'])
					# fieldmappings.addTable(relatedTable)
					# fieldList = arcpy.ListFields(relatedTable)
					# noFunctionalFieldName = fieldList[len(fieldList)-1].name
					# arcpy.AddMessage("noFunctionalFieldName: {0}".format(noFunctionalFieldName))
					# fieldmap = fieldmappings.getFieldMap(fieldmappings.findFieldMapIndex(noFunctionalFieldName))
					# fieldmap.addInputField(relatedTable, "wikiURL")
					# fieldmap.addInputField(inputFeatureClassName, "URL")
					# fieldmappings.replaceFieldMap(fieldmappings.findFieldMapIndex(noFunctionalFieldName), fieldmap)

				in_stat_fields.values = noFunctionalPropertyTable



				# fieldmappings.removeFieldMap(fieldmappings.findFieldMapIndex("wikiURL"))



				# in_field_mapping.value = fieldmappings.exportToString()

			# if in_stat_fields.altered:
			# 	fieldMergeRuleTest = in_stat_fields.valueAsText
			# 	if fieldMergeRuleTest:
			# 	fieldSplitList = fieldMergeRuleTest.split(";")
			# 	for fieldSplitItem in fieldSplitList:
			# 		fieldMergeList = fieldSplitList.split("\t")
			# 		for item in MergeNoFunctionalProperty.relatedTableFieldList:
			# 			if item[]








			

		return

	def updateMessages(self, parameters):
		"""Modify the messages created by internal validation for each tool
		parameter.  This method is called after internal validation."""
		return

	def execute(self, parameters, messages):
		"""The source code of the tool."""
		in_wikiplace_IRI = parameters[0]
		in_stat_fields = parameters[1]
		# out_location = parameters[2]
		# out_points_name = parameters[3]

		
		if in_wikiplace_IRI.value:
			inputFeatureClassName = in_wikiplace_IRI.valueAsText
			# outLocation = out_location.valueAsText
			# outFeatureClassName = out_points_name.valueAsText
			fieldMergeRuleTest = in_stat_fields.valueAsText

			# messages.addErrorMessage("in_stat_fields.values: {0}".format(in_stat_fields.values))
			# messages.addErrorMessage("MergeNoFunctionalProperty.relatedTableFieldList: {0}".format(MergeNoFunctionalProperty.relatedTableFieldList))

			

			
			# fieldmappings = in_field_mapping.valueAsText

			lastIndexOFGDB = inputFeatureClassName.rfind("\\")
			currentWorkspace = inputFeatureClassName[:lastIndexOFGDB]

			if currentWorkspace.endswith(".gdb") == False:
				messages.addErrorMessage("Please enter a feature class in file geodatabase for the input feature class.")
				raise arcpy.ExecuteError
			else:
				# if in_related_table.value:
				arcpy.env.workspace = currentWorkspace
				# relatedTableList = UTIL.getRelatedTableFromFeatureClass(inputFeatureClassName)
				# fieldmappings = arcpy.FieldMappings()
				# fieldmappings.addTable(inputFeatureClassName)
				# for relatedTable in relatedTableList:
				# 	fieldmappings.addTable(relatedTable)
				# 	fieldList = arcpy.ListFields(relatedTable)
				# 	fieldName = fieldList[len(fieldList)-1].name
				# 	arcpy.AddMessage("fieldName: {0}".format(fieldName))


				# fieldmappings.removeFieldMap(fieldmappings.findFieldMapIndex("wikiURL"))

				# arcpy.AddMessage("fieldmappings: {0}".format(fieldmappings))
				# if out_location.value and out_points_name.value:
				# 	arcpy.FeatureClassToFeatureClass_conversion(inputFeatureClassName, outLocation, outFeatureClassName, "", fieldmappings)

				# get the ValueTable(fieldName, merge rule, related table full path) 
				fieldMergeRuleFileNameList = []

				if fieldMergeRuleTest:
					fieldSplitList = fieldMergeRuleTest.split(";")
					for fieldSplitItem in fieldSplitList:
						fieldMergeList = fieldSplitItem.split(" ", 2)
						fieldMergeRuleFileNameList.append(fieldMergeList)

				arcpy.AddMessage("fieldMergeRuleFileNameList: {0}".format(fieldMergeRuleFileNameList))

				for fieldMergeRuleFileNameItem in fieldMergeRuleFileNameList:
					appendFieldName = fieldMergeRuleFileNameItem[0]
					mergeRule = fieldMergeRuleFileNameItem[1]
					relatedTableName = fieldMergeRuleFileNameItem[2].replace("'", "")

					noFunctionalPropertyDict = UTIL.buildMultiValueDictFromNoFunctionalProperty(appendFieldName, relatedTableName)
					if noFunctionalPropertyDict != -1:
						UTIL.appendFieldInFeatureClassByMergeRule(inputFeatureClassName, noFunctionalPropertyDict, appendFieldName, relatedTableName, mergeRule)

				# UTIL.buildMultiValueDictFromNoFunctionalProperty(fieldName, tableName)
				# UTIL.appendFieldInFeatureClassByMergeRule(inputFeatureClassName, noFunctionalPropertyDict, appendFieldName, relatedTableName, mergeRule)

		return


class MergeSingleNoFunctionalProperty(object):
	relatedTableFieldList = []
	relatedTableList = []
	relatedNoFunctionalPropertyURLList = []
	def __init__(self):
		"""Define the tool (tool name is the name of the class)."""
		self.label = "Linked Data Single No Functional Property Merge"
		self.description = """The related seperated tables from Linked Data Location Entities Property Enrichment Tool have multivalue for each wikidata location because the coresponding property is not functional property. 
		This Tool helps user to merge these multivalue to a single record and add it to original feature class sttribute table by using merge rules which are specified by users."""
		self.canRunInBackground = False
		
	def getParameterInfo(self):
		"""Define parameter definitions"""
		# The input Feature class which is the output of LinkedDataAnalysis Tool, "URL" column should be included in the attribute table
		in_wikiplace_IRI = arcpy.Parameter(
			displayName="Input wikidata location entities Feature Class",
			name="in_wikiplace_IRI",
			datatype="DEFeatureClass",
			parameterType="Required",
			direction="Input")

		in_wikiplace_IRI.filter.list = ["Point"]

		in_no_functional_property_list = arcpy.Parameter(
			displayName="List of No-Functional Properties of Current Feature Class",
			name="in_no_functional_property_list",
			datatype="GPString",
			parameterType="Required",
			direction="Input")

		in_no_functional_property_list.filter.type = "ValueList"
		in_no_functional_property_list.filter.list = []

		in_related_table_list = arcpy.Parameter(
			displayName="List of Related Tables",
			name="in_related_table_list",
			datatype="GPString",
			parameterType="Required",
			direction="Input")

		in_related_table_list.filter.type = "ValueList"
		in_related_table_list.filter.list = []

		in_merge_rule = arcpy.Parameter(
		displayName='List of Merge Rules',
		name='in_merge_rule',
		datatype='GPString',
		parameterType='Required',
		direction='Input')

		in_merge_rule.filter.type = "ValueList"
		in_merge_rule.filter.list = ['SUM', 'MIN', 'MAX', 'STDEV', 'MEAN', 'COUNT', 'FIRST', 'LAST', 'CONCATENATE']

		in_cancatenate_delimiter = arcpy.Parameter(
		displayName='The delimiter of cancatenating fields',
		name='in_cancatenate_delimiter',
		datatype='GPString',
		parameterType='Optional',
		direction='Input')

		in_cancatenate_delimiter.filter.type = "ValueList"
		in_cancatenate_delimiter.filter.list = ['DASH', 'COMMA', 'VERTICAL BAR', 'TAB', 'SPACE']
		in_cancatenate_delimiter.enabled = False

		params = [in_wikiplace_IRI, in_no_functional_property_list, in_related_table_list, in_merge_rule, in_cancatenate_delimiter]

		return params



	def isLicensed(self):
		"""Set whether tool is licensed to execute."""
		return True

	def updateParameters(self, parameters):
		"""Modify the values and properties of parameters before internal
		validation is performed.  This method is called whenever a parameter
		has been changed."""
		in_wikiplace_IRI = parameters[0]
		in_no_functional_property_list = parameters[1]
		in_related_table_list = parameters[2]
		in_merge_rule = parameters[3]
		in_cancatenate_delimiter = parameters[4]
		
		if in_wikiplace_IRI.altered:
			inputFeatureClassName = in_wikiplace_IRI.valueAsText
			lastIndexOFGDB = inputFeatureClassName.rfind("\\")
			featureClassName = inputFeatureClassName[(lastIndexOFGDB+1):]
			currentWorkspace = inputFeatureClassName[:lastIndexOFGDB]

			if currentWorkspace.endswith(".gdb") == False:
				messages.addErrorMessage("Please enter a feature class in file geodatabase for the input feature class.")
				raise arcpy.ExecuteError
			else:
				# if in_related_table.value:
				arcpy.env.workspace = currentWorkspace
				# out_location.value = currentWorkspace
				# out_points_name.value = featureClassName + "_noFunc_merge"
				# # check whether the input table are in the same file geodatabase as the input feature class
				# inputTableName = in_related_table.valueAsText
				# lastIndexOFTable = inputTableName.rfind("\\")
				# currentWorkspaceTable = inputTableName[:lastIndexOFTable]
				# if currentWorkspaceTable != currentWorkspace:
				# 	messages.addErrorMessage("Please enter a table in the same file geodatabase as the input feature class.")
				# 	raise arcpy.ExecuteError
				# else:
				# 	if UTIL.detectRelationship(inputFeatureClassName, inputTableName):
				# 		arcpy.AddMessage("The feature class and table are related!")
				MergeSingleNoFunctionalProperty.relatedTableFieldList = []
				MergeSingleNoFunctionalProperty.relatedTableList = []
				MergeSingleNoFunctionalProperty.relatedNoFunctionalPropertyURLList = []

				MergeSingleNoFunctionalProperty.relatedTableList = UTIL.getRelatedTableFromFeatureClass(inputFeatureClassName)
				in_related_table_list.filter.list = MergeSingleNoFunctionalProperty.relatedTableList
				
				# noFunctionalPropertyTable = []

				for relatedTable in MergeSingleNoFunctionalProperty.relatedTableList:
					fieldList = arcpy.ListFields(relatedTable)
					if "origin" not in fieldList and "end" not in fieldList:
						noFunctionalFieldName = fieldList[2].name
						arcpy.AddMessage("noFunctionalFieldName: {0}".format(noFunctionalFieldName))
						MergeSingleNoFunctionalProperty.relatedTableFieldList.append(noFunctionalFieldName)
						# get the no functioal property URL from the firt row of this table field "propURL"
						# propURL = arcpy.da.SearchCursor(relatedTable, ("propURL")).next()[0]

						TableRelationshipClassList = UTIL.getRelationshipClassFromTable(relatedTable)
						propURL = arcpy.Describe(TableRelationshipClassList[0]).forwardPathLabel

						MergeSingleNoFunctionalProperty.relatedNoFunctionalPropertyURLList.append(propURL)

				in_no_functional_property_list.filter.list = MergeSingleNoFunctionalProperty.relatedNoFunctionalPropertyURLList
						# noFunctionalPropertyTable.append([noFunctionalFieldName, 'COUNT', relatedTable])
						# MergeNoFunctionalProperty.relatedTableFieldList.append([noFunctionalFieldName, relatedTable, 'COUNT'])
					# fieldmappings.addTable(relatedTable)
					# fieldList = arcpy.ListFields(relatedTable)
					# noFunctionalFieldName = fieldList[len(fieldList)-1].name
					# arcpy.AddMessage("noFunctionalFieldName: {0}".format(noFunctionalFieldName))

				# in_stat_fields.values = noFunctionalPropertyTable

		if in_no_functional_property_list.altered:
			selectPropURL = in_no_functional_property_list.valueAsText
			selectIndex = MergeSingleNoFunctionalProperty.relatedNoFunctionalPropertyURLList.index(selectPropURL)
			selectFieldName = MergeSingleNoFunctionalProperty.relatedTableFieldList[selectIndex]
			selectTableName = MergeSingleNoFunctionalProperty.relatedTableList[selectIndex]

			in_related_table_list.value = selectTableName

			currentDataType = UTIL.getFieldDataTypeInTable(selectFieldName, selectTableName)
			if currentDataType in ['Single', 'Double', 'SmallInteger', 'Integer']:
				in_merge_rule.filter.list = ['SUM', 'MIN', 'MAX', 'STDEV', 'MEAN', 'COUNT', 'FIRST', 'LAST', 'CONCATENATE']
			# elif currentDataType in ['SmallInteger', 'Integer']:
			# 	in_merge_rule.filter.list = ['SUM', 'MIN', 'MAX', 'COUNT', 'FIRST', 'LAST']
			else:
				in_merge_rule.filter.list = ['COUNT', 'FIRST', 'LAST', 'CONCATENATE']

		if in_related_table_list.altered:
			selectTableName = in_related_table_list.valueAsText
			selectIndex = MergeSingleNoFunctionalProperty.relatedTableList.index(selectTableName)
			selectFieldName = MergeSingleNoFunctionalProperty.relatedTableFieldList[selectIndex]
			selectPropURL = MergeSingleNoFunctionalProperty.relatedNoFunctionalPropertyURLList[selectIndex]

			in_no_functional_property_list.value = selectPropURL

			currentDataType = UTIL.getFieldDataTypeInTable(selectFieldName, selectTableName)
			if currentDataType in ['Single', 'Double', 'SmallInteger', 'Integer']:
				in_merge_rule.filter.list = ['SUM', 'MIN', 'MAX', 'STDEV', 'MEAN', 'COUNT', 'FIRST', 'LAST', 'CONCATENATE']
			# elif currentDataType in ['SmallInteger', 'Integer']:
			# 	in_merge_rule.filter.list = ['SUM', 'MIN', 'MAX', 'COUNT', 'FIRST', 'LAST']
			else:
				in_merge_rule.filter.list = ['COUNT', 'FIRST', 'LAST', 'CONCATENATE']
			

		if in_merge_rule.valueAsText == "CONCATENATE":
			in_cancatenate_delimiter.enabled = True




		return

	def updateMessages(self, parameters):
		"""Modify the messages created by internal validation for each tool
		parameter.  This method is called after internal validation."""
		return

	def execute(self, parameters, messages):
		"""The source code of the tool."""
		in_wikiplace_IRI = parameters[0]
		in_no_functional_property_list = parameters[1]
		in_related_table_list = parameters[2]
		in_merge_rule = parameters[3]
		in_cancatenate_delimiter = parameters[4]

		
		if in_wikiplace_IRI.value:
			inputFeatureClassName = in_wikiplace_IRI.valueAsText
			selectPropURL = in_no_functional_property_list.valueAsText
			selectTableName = in_related_table_list.valueAsText
			selectMergeRule = in_merge_rule.valueAsText

			selectIndex = MergeSingleNoFunctionalProperty.relatedTableList.index(selectTableName)
			selectFieldName = MergeSingleNoFunctionalProperty.relatedTableFieldList[selectIndex]

			arcpy.AddMessage("CurrentDataType: {0}".format(UTIL.getFieldDataTypeInTable(selectFieldName, selectTableName)))

			arcpy.AddMessage("selectTableName: {0}".format(selectTableName))

			arcpy.AddMessage("MergeSingleNoFunctionalProperty.relatedTableList: {0}".format(MergeSingleNoFunctionalProperty.relatedTableList))

			arcpy.AddMessage("MergeSingleNoFunctionalProperty.relatedTableList.index(selectTableName): {0}".format(MergeSingleNoFunctionalProperty.relatedTableList.index(selectTableName)))

			



			
			lastIndexOFGDB = inputFeatureClassName.rfind("\\")
			currentWorkspace = inputFeatureClassName[:lastIndexOFGDB]

			if currentWorkspace.endswith(".gdb") == False:
				messages.addErrorMessage("Please enter a feature class in file geodatabase for the input feature class.")
				raise arcpy.ExecuteError
			else:
				# if in_related_table.value:
				arcpy.env.workspace = currentWorkspace
				

				noFunctionalPropertyDict = UTIL.buildMultiValueDictFromNoFunctionalProperty(selectFieldName, selectTableName)

				if noFunctionalPropertyDict != -1:
					if selectMergeRule == 'CONCATENATE':
						selectDelimiter = in_cancatenate_delimiter.valueAsText
						delimiter = ','

						# ['DASH', 'COMMA', 'VERTICAL BAR', 'TAB', 'SPACE']
						if selectDelimiter == 'DASH':
							delimiter = '-'
						elif selectDelimiter == 'COMMA':
							delimiter = ','
						elif selectDelimiter == 'VERTICAL BAR':
							delimiter = '|'
						elif selectDelimiter == 'TAB':
							delimiter = '	'
						elif selectDelimiter == 'SPACE':
							delimiter = ' '

						UTIL.appendFieldInFeatureClassByMergeRule(inputFeatureClassName, noFunctionalPropertyDict, selectFieldName, selectTableName, selectMergeRule, delimiter)
					else:
						UTIL.appendFieldInFeatureClassByMergeRule(inputFeatureClassName, noFunctionalPropertyDict, selectFieldName, selectTableName, selectMergeRule, '')


				# fieldMergeRuleFileNameList = []

				# if fieldMergeRuleTest:
				# 	fieldSplitList = fieldMergeRuleTest.split(";")
				# 	for fieldSplitItem in fieldSplitList:
				# 		fieldMergeList = fieldSplitItem.split(" ", 2)
				# 		fieldMergeRuleFileNameList.append(fieldMergeList)

				# arcpy.AddMessage("fieldMergeRuleFileNameList: {0}".format(fieldMergeRuleFileNameList))

				# for fieldMergeRuleFileNameItem in fieldMergeRuleFileNameList:
				# 	appendFieldName = fieldMergeRuleFileNameItem[0]
				# 	mergeRule = fieldMergeRuleFileNameItem[1]
				# 	relatedTableName = fieldMergeRuleFileNameItem[2].replace("'", "")

				# 	noFunctionalPropertyDict = UTIL.buildMultiValueDictFromNoFunctionalProperty(appendFieldName, relatedTableName)
				# 	if noFunctionalPropertyDict != -1:
				# 		UTIL.appendFieldInFeatureClassByMergeRule(inputFeatureClassName, noFunctionalPropertyDict, appendFieldName, relatedTableName, mergeRule)

				# UTIL.buildMultiValueDictFromNoFunctionalProperty(fieldName, tableName)
				# UTIL.appendFieldInFeatureClassByMergeRule(inputFeatureClassName, noFunctionalPropertyDict, appendFieldName, relatedTableName, mergeRule)

		return

# class MergeNoFunctionalProperty(object):
# 	def __init__(self):
# 		"""Define the tool (tool name is the name of the class)."""
# 		self.label = "Linked Data Multivalue No Functional Property Merge"
# 		self.description = """The related seperated tables from Linked Data Location Entities Property Enrichment Tool have multivalue for each wikidata location because the coresponding property is not functional property. 
# 		This Tool helps user to merge these multivalue to a single record and add it to original feature class sttribute table by using merge rules which are specified by users."""
# 		self.canRunInBackground = False
		
# 	def getParameterInfo(self):
# 		"""Define parameter definitions"""
# 		# The input Feature class which is the output of LinkedDataAnalysis Tool, "URL" column should be included in the attribute table
# 		in_wikiplace_IRI = arcpy.Parameter(
# 			displayName="Input wikidata location entities Feature Class",
# 			name="in_wikiplace_IRI",
# 			datatype="DEFeatureClass",
# 			parameterType="Required",
# 			direction="Input")

# 		in_wikiplace_IRI.filter.list = ["Point"]

# 		# in_related_table = arcpy.Parameter(
# 		# 	displayName="Input no-functional property table which should be related to the input Feature Class",
# 		# 	name="in_related_table",
# 		# 	datatype="DETable",
# 		# 	parameterType="Required",
# 		# 	direction="Input")

# 		in_field_mapping = arcpy.Parameter(
# 			displayName="Field Mapping From no-functional properties in all feature class related tables",
# 			name="in_field_mapping",
# 			datatype="GPFieldMapping",
# 			parameterType="Optional",
# 			direction="Input")

# 		out_location = arcpy.Parameter(
# 			displayName="Output Location",
# 			name="out_location",
# 			datatype="DEWorkspace",
# 			parameterType="Required",
# 			direction="Input")

# 		out_location.value = os.path.dirname(__file__)

# 		# Derived Output Point Feature Class Name
# 		out_points_name = arcpy.Parameter(
# 			displayName="Output Point Feature Class Name with No-Functional Property Merged Values",
# 			name="out_points_name",
# 			datatype="GPString",
# 			parameterType="Required",
# 			direction="Input")

# 		params = [in_wikiplace_IRI, in_field_mapping,out_location, out_points_name]

# 		return params



# 	def isLicensed(self):
# 		"""Set whether tool is licensed to execute."""
# 		return True

# 	def updateParameters(self, parameters):
# 		"""Modify the values and properties of parameters before internal
# 		validation is performed.  This method is called whenever a parameter
# 		has been changed."""
# 		in_wikiplace_IRI = parameters[0]
# 		in_field_mapping = parameters[1]
# 		out_location = parameters[2]
# 		out_points_name = parameters[3]
		
# 		if in_wikiplace_IRI.value:
# 			inputFeatureClassName = in_wikiplace_IRI.valueAsText
# 			lastIndexOFGDB = inputFeatureClassName.rfind("\\")
# 			featureClassName = inputFeatureClassName[(lastIndexOFGDB+1):]
# 			currentWorkspace = inputFeatureClassName[:lastIndexOFGDB]

# 			if currentWorkspace.endswith(".gdb") == False:
# 				messages.addErrorMessage("Please enter a feature class in file geodatabase for the input feature class.")
# 				raise arcpy.ExecuteError
# 			else:
# 				# if in_related_table.value:
# 				arcpy.env.workspace = currentWorkspace
# 				out_location.value = currentWorkspace
# 				out_points_name.value = featureClassName + "_noFunc_merge"
# 				# # check whether the input table are in the same file geodatabase as the input feature class
# 				# inputTableName = in_related_table.valueAsText
# 				# lastIndexOFTable = inputTableName.rfind("\\")
# 				# currentWorkspaceTable = inputTableName[:lastIndexOFTable]
# 				# if currentWorkspaceTable != currentWorkspace:
# 				# 	messages.addErrorMessage("Please enter a table in the same file geodatabase as the input feature class.")
# 				# 	raise arcpy.ExecuteError
# 				# else:
# 				# 	if UTIL.detectRelationship(inputFeatureClassName, inputTableName):
# 				# 		arcpy.AddMessage("The feature class and table are related!")
# 				relatedTableList = UTIL.getRelatedTableFromFeatureClass(inputFeatureClassName)
# 				fieldmappings = arcpy.FieldMappings()
# 				fieldmappings.addTable(inputFeatureClassName)
# 				for relatedTable in relatedTableList:
# 					fieldmappings.addTable(relatedTable)
# 					# fieldList = arcpy.ListFields(relatedTable)
# 					# noFunctionalFieldName = fieldList[len(fieldList)-1].name
# 					# arcpy.AddMessage("noFunctionalFieldName: {0}".format(noFunctionalFieldName))
# 					# fieldmap = fieldmappings.getFieldMap(fieldmappings.findFieldMapIndex(noFunctionalFieldName))
# 					# fieldmap.addInputField(relatedTable, "wikiURL")
# 					# fieldmap.addInputField(inputFeatureClassName, "URL")
# 					# fieldmappings.replaceFieldMap(fieldmappings.findFieldMapIndex(noFunctionalFieldName), fieldmap)




# 				fieldmappings.removeFieldMap(fieldmappings.findFieldMapIndex("wikiURL"))



# 				in_field_mapping.value = fieldmappings.exportToString()







			

# 		return

# 	def updateMessages(self, parameters):
# 		"""Modify the messages created by internal validation for each tool
# 		parameter.  This method is called after internal validation."""
# 		return

# 	def execute(self, parameters, messages):
# 		"""The source code of the tool."""
# 		in_wikiplace_IRI = parameters[0]
# 		in_field_mapping = parameters[1]
# 		out_location = parameters[2]
# 		out_points_name = parameters[3]

		
# 		if in_wikiplace_IRI.value:
# 			inputFeatureClassName = in_wikiplace_IRI.valueAsText
# 			outLocation = out_location.valueAsText
# 			outFeatureClassName = out_points_name.valueAsText
# 			fieldmappings = in_field_mapping.valueAsText

# 			lastIndexOFGDB = inputFeatureClassName.rfind("\\")
# 			currentWorkspace = inputFeatureClassName[:lastIndexOFGDB]

# 			if currentWorkspace.endswith(".gdb") == False:
# 				messages.addErrorMessage("Please enter a feature class in file geodatabase for the input feature class.")
# 				raise arcpy.ExecuteError
# 			else:
# 				# if in_related_table.value:
# 				arcpy.env.workspace = currentWorkspace
# 				# relatedTableList = UTIL.getRelatedTableFromFeatureClass(inputFeatureClassName)
# 				# fieldmappings = arcpy.FieldMappings()
# 				# fieldmappings.addTable(inputFeatureClassName)
# 				# for relatedTable in relatedTableList:
# 				# 	fieldmappings.addTable(relatedTable)
# 				# 	fieldList = arcpy.ListFields(relatedTable)
# 				# 	fieldName = fieldList[len(fieldList)-1].name
# 				# 	arcpy.AddMessage("fieldName: {0}".format(fieldName))


# 				# fieldmappings.removeFieldMap(fieldmappings.findFieldMapIndex("wikiURL"))

# 				# arcpy.AddMessage("fieldmappings: {0}".format(fieldmappings))
# 				if out_location.value and out_points_name.value:
# 					arcpy.FeatureClassToFeatureClass_conversion(inputFeatureClassName, outLocation, outFeatureClassName, "", fieldmappings)
				
		

# 		return







class LocationPropertyPath(object):
	locationCommonPropertyDict = dict()
	locationCommonPropertyNameCountList = []
	locationCommonPropertyURLList = []
	locationCommonPropertyCountList = []
	def __init__(self):
		"""Define the tool (tool name is the name of the class)."""
		self.label = "Linked Data Location Linkage Exploration"
		self.description = """This Tool enables the users to explore the linkages between locations in wikidata. 
		Given an input feature class, this tool gets all properties whose objects are also locations. 
		The output is another feature class which contains the locations which are linked to the locations of input feature class."""
		self.canRunInBackground = False
		
	def getParameterInfo(self):
		"""Define parameter definitions"""
		# The input Feature class which is the output of LinkedDataAnalysis Tool, "URL" column should be included in the attribute table
		in_wikiplace_IRI = arcpy.Parameter(
			displayName="Input wikidata location entities Feature Class",
			name="in_wikiplace_IRI",
			datatype="DEFeatureClass",
			parameterType="Required",
			direction="Input")

		in_wikiplace_IRI.filter.list = ["Point"]

		# Choose property which links to a locations
		in_location_property = arcpy.Parameter(
			displayName="Input Property which represents location relationships",
			name="in_location_property",
			datatype="GPString",
			parameterType="Required",
			direction="Input")

		in_location_property.filter.type = "ValueList"
		in_location_property.filter.list = []

		# Enter the degree of relationship between these location features. Like 2-degree sister city relationship
		in_relation_degree = arcpy.Parameter(
			displayName="Input Relationship Degree",
			name="in_relation_degree",
			datatype="GPLong",
			parameterType="Required",
			direction="Input")

		in_relation_degree.value = 1

		out_location = arcpy.Parameter(
			displayName="Output Location",
			name="out_location",
			datatype="DEWorkspace",
			parameterType="Required",
			direction="Input")

		out_location.value = os.path.dirname(__file__)

		# Derived Output Point Feature Class Name
		out_points_name = arcpy.Parameter(
			displayName="Output Point Feature Class Name",
			name="out_points_name",
			datatype="GPString",
			parameterType="Required",
			direction="Input")

		params = [in_wikiplace_IRI, in_location_property,in_relation_degree, out_location, out_points_name]

		return params



	def isLicensed(self):
		"""Set whether tool is licensed to execute."""
		return True

	def updateParameters(self, parameters):
		"""Modify the values and properties of parameters before internal
		validation is performed.  This method is called whenever a parameter
		has been changed."""
		in_wikiplace_IRI = parameters[0]
		in_location_property = parameters[1]
		in_relation_degree = parameters[2]
		out_location = parameters[3]
		out_points_name = parameters[4]
		
		if in_wikiplace_IRI.value:
			inputFeatureClassName = in_wikiplace_IRI.valueAsText
			lastIndexOFGDB = inputFeatureClassName.rfind("\\")
			featureClassName = inputFeatureClassName[(lastIndexOFGDB+1):]
			currentWorkspace = inputFeatureClassName[:lastIndexOFGDB]

			arcpy.env.workspace = currentWorkspace
			out_location.value = currentWorkspace

			# get all the IRI from input point feature class of wikidata places
			inplaceIRIList = []
			cursor = arcpy.SearchCursor(inputFeatureClassName)
			for row in cursor:
				inplaceIRIList.append(row.getValue("URL"))
			
			# get all the property URL which are used in the input feature class. their objects are geographic locations which have coordinates, I call them location common properties
			locationCommonPropertyJSONObj = SPARQLQuery.locationCommonPropertyQuery(inplaceIRIList)
			locationCommonPropertyJSON = locationCommonPropertyJSONObj["results"]["bindings"]

			LocationPropertyPath.locationCommonPropertyURLList = []
			LocationPropertyPath.locationCommonPropertyCountList = []
			for jsonItem in locationCommonPropertyJSON:
				LocationPropertyPath.locationCommonPropertyURLList.append(jsonItem["p"]["value"])
				LocationPropertyPath.locationCommonPropertyCountList.append(jsonItem["NumofSub"]["value"])

			locationCommonPropertyCountDict = dict(zip(LocationPropertyPath.locationCommonPropertyURLList, LocationPropertyPath.locationCommonPropertyCountList))

			# get the english label for each location common property
			locationCommonPropertyLabelJSON = SPARQLQuery.locationCommonPropertyLabelQuery(LocationPropertyPath.locationCommonPropertyURLList)
			# locationCommonPropertyLabelJSON = locationCommonPropertyLabelJSONObj["results"]["bindings"]

			# a dictionary object: key: propertyNameCount, value: propertyURL
			LocationPropertyPath.locationCommonPropertyDict = dict()
			LocationPropertyPath.locationCommonPropertyNameCountList = []
			LocationPropertyPath.locationCommonPropertyURLList = []
			LocationPropertyPath.locationCommonPropertyCountList = []

			for jsonItem in locationCommonPropertyLabelJSON:
				propertyURL = jsonItem["p"]["value"]
				LocationPropertyPath.locationCommonPropertyURLList.append(propertyURL)

				propertyName = jsonItem["propertyLabel"]["value"]

				propertyCount = locationCommonPropertyCountDict[propertyURL]
				LocationPropertyPath.locationCommonPropertyCountList.append(propertyCount)

				propertyNameCount = propertyName + "(" + propertyCount + ")"
				LocationPropertyPath.locationCommonPropertyNameCountList.append(propertyNameCount)
				LocationPropertyPath.locationCommonPropertyDict[propertyNameCount] = propertyURL

			in_location_property.filter.list = LocationPropertyPath.locationCommonPropertyNameCountList






			if in_location_property.value and in_relation_degree.value and out_points_name.valueAsText == None:
				propertyName = in_location_property.valueAsText
				relationdegree  = in_relation_degree.valueAsText

				lastIndex = propertyName.rfind("(")
				propertyName = propertyName[:lastIndex]

				propertyName = propertyName.replace(" ", "_")

				if featureClassName.endswith(".shp"):
					lastIndex = featureClassName.rfind(".")
					featureClassNameNoShp = featureClassName[:lastIndex]
					out_points_name.value = featureClassNameNoShp + "_D" + relationdegree + "_" + propertyName + ".shp"
				else:
					out_points_name.value = featureClassName + "_D" + relationdegree + "_" + propertyName


				if arcpy.Exists(out_points_name.valueAsText):
					arcpy.AddError("The output feature class name already exists in current workspace!")
					raise arcpy.ExecuteError

			


			if in_relation_degree.value:
				relationDegree = int(in_relation_degree.valueAsText)
				if relationDegree > 4:
					in_relation_degree.value = 4





			

		return

	def updateMessages(self, parameters):
		"""Modify the messages created by internal validation for each tool
		parameter.  This method is called after internal validation."""
		return

	def execute(self, parameters, messages):
		"""The source code of the tool."""
		in_wikiplace_IRI = parameters[0]
		in_location_property = parameters[1]
		in_relation_degree = parameters[2]
		out_location = parameters[3]
		out_points_name = parameters[4]

		
		if in_wikiplace_IRI.value:
			inputFeatureClassName = in_wikiplace_IRI.valueAsText
			locationCommonPropertyNameCount = in_location_property.valueAsText
			relationDegree = int(in_relation_degree.valueAsText)
			outLocation = out_location.valueAsText
			outFeatureClassName = out_points_name.valueAsText
			
			lastIndexOFGDB = inputFeatureClassName.rfind("\\")
			originFeatureClassName = inputFeatureClassName[(lastIndexOFGDB+1):]

			if outLocation.endswith(".gdb") == False:
				messages.addErrorMessage("Please enter a file geodatabase as the file location for output feature class.")
				raise arcpy.ExecuteError
			else:
				arcpy.env.workspace = outLocation

				endFeatureClassName = outLocation + "\\" + outFeatureClassName
				if arcpy.Exists(endFeatureClassName):
					messages.addErrorMessage("The output feature class name already exists in current workspace!")
					raise arcpy.ExecuteError
				else:

					# get all the IRI from input point feature class of wikidata places
					inplaceIRIList = []
					cursor = arcpy.SearchCursor(inputFeatureClassName)
					for row in cursor:
						inplaceIRIList.append(row.getValue("URL"))

					if relationDegree > 4:
						relationDegree = 4
						in_relation_degree.value = 4
					
					locationCommonPropertyURL = LocationPropertyPath.locationCommonPropertyDict[locationCommonPropertyNameCount]
					locationLinkageRelationJSONObj = SPARQLQuery.locationLinkageRelationQuery(inplaceIRIList, locationCommonPropertyURL, relationDegree)
					locationLinkageRelationJSON = locationLinkageRelationJSONObj["results"]["bindings"]

					endPlaceIRISet = Set()
					for jsonItem in locationLinkageRelationJSON:
						endPlaceIRISet.add(jsonItem["end"]["value"])

					endPlaceIRIList = list(endPlaceIRISet)

					# endPlaceJSONObj = SPARQLQuery.endPlaceInformationQuery(endPlaceIRIList)
					
					endPlaceJSON = SPARQLQuery.endPlaceInformationQuery(endPlaceIRIList)

					Json2Field.creatPlaceFeatureClassFromJSON(endPlaceJSON, endFeatureClassName, None, "")


					lastIndex = locationCommonPropertyNameCount.rfind("(")
					locationCommonPropertyName = locationCommonPropertyNameCount[:lastIndex]
					locationLinkageTableName = Json2Field.createLocationLinkageMappingTableFromJSON(locationLinkageRelationJSON, "origin", "end", inputFeatureClassName, endFeatureClassName, locationCommonPropertyURL, locationCommonPropertyName, relationDegree)

					endFeatureRelationshipClassName = outFeatureClassName + "_" + locationLinkageTableName + "_RelClass"
					arcpy.CreateRelationshipClass_management(outFeatureClassName, locationLinkageTableName, endFeatureRelationshipClassName, "SIMPLE",
						"is "+ locationCommonPropertyName + "of", locationCommonPropertyName,
										 "FORWARD", "ONE_TO_MANY", "NONE", "URL", "end")

					originFeatureRelationshipClassName = originFeatureClassName + "_" + locationLinkageTableName + "_RelClass"
					arcpy.CreateRelationshipClass_management(originFeatureClassName, locationLinkageTableName, originFeatureRelationshipClassName, "SIMPLE",
						locationCommonPropertyName, "is "+ locationCommonPropertyName + "of",
										 "FORWARD", "ONE_TO_MANY", "NONE", "URL", "origin")
				
		

		return



class RelFinder(object):
	firstPropertyLabelURLDict = dict()
	secondPropertyLabelURLDict = dict()
	thirdPropertyLabelURLDict = dict()
	fourthPropertyLabelURLDict = dict()
	def __init__(self):
		"""Define the tool (tool name is the name of the class)."""
		self.label = "Linked Data Relationship Finder from Location Features"
		self.description = """Getting a table of S-P-O triples for the relationships from locations features."""
		self.canRunInBackground = False
		
	def getParameterInfo(self):
		"""Define parameter definitions"""
		# The input Feature class which is the output of LinkedDataAnalysis Tool, "URL" column should be included in the attribute table
		in_wikiplace_IRI = arcpy.Parameter(
			displayName="Input wikidata location entities Feature Class",
			name="in_wikiplace_IRI",
			datatype="DEFeatureClass",
			parameterType="Required",
			direction="Input")

		in_wikiplace_IRI.filter.list = ["Point"]

		in_relation_degree = arcpy.Parameter(
			displayName="Relationship Degree",
			name="in_relation_degree",
			datatype="GPLong",
			parameterType="Required",
			direction="Input")

		in_relation_degree.filter.type = "ValueList"
		in_relation_degree.filter.list = [1, 2, 3, 4]

		# Choose the first degree property direction which links to a locations, "ORIGIN" means in_wikiplace_IRI are origins, "DESTINATION" means in_wikiplace_IRI are destinations
		in_first_property_dir = arcpy.Parameter(
			displayName="The first degree property direction",
			name="in_first_property_dir",
			datatype="GPString",
			parameterType="Required",
			direction="Input")

		in_first_property_dir.filter.type = "ValueList"
		in_first_property_dir.filter.list = ["BOTH", "ORIGIN", "DESTINATION"]

		# Choose the first degree property which links to a locations
		in_first_property = arcpy.Parameter(
			displayName="The first degree property",
			name="in_first_property",
			datatype="GPString",
			parameterType="Optional",
			direction="Input")

		in_first_property.filter.type = "ValueList"
		in_first_property.filter.list = []

		# Choose the second degree property direction which links to a locations, "ORIGIN" means in_wikiplace_IRI are origins, "DESTINATION" means in_wikiplace_IRI are destinations
		in_second_property_dir = arcpy.Parameter(
			displayName="The second degree property direction",
			name="in_second_property_dir",
			datatype="GPString",
			parameterType="Optional",
			direction="Input")

		in_second_property_dir.filter.type = "ValueList"
		in_second_property_dir.filter.list = ["BOTH", "ORIGIN", "DESTINATION"]
		in_second_property_dir.enabled = False

		# Choose the second degree property which links to a locations
		in_second_property = arcpy.Parameter(
			displayName="The second degree property",
			name="in_second_property",
			datatype="GPString",
			parameterType="Optional",
			direction="Input")

		in_second_property.filter.type = "ValueList"
		in_second_property.filter.list = []
		in_second_property.enabled = False

		# Choose the third degree property direction which links to a locations, "ORIGIN" means in_wikiplace_IRI are origins, "DESTINATION" means in_wikiplace_IRI are destinations
		in_third_property_dir = arcpy.Parameter(
			displayName="The third degree property direction",
			name="in_third_property_dir",
			datatype="GPString",
			parameterType="Optional",
			direction="Input")

		in_third_property_dir.filter.type = "ValueList"
		in_third_property_dir.filter.list = ["BOTH", "ORIGIN", "DESTINATION"]
		in_third_property_dir.enabled = False

		# Choose the third degree property which links to a locations
		in_third_property = arcpy.Parameter(
			displayName="The third degree property",
			name="in_third_property",
			datatype="GPString",
			parameterType="Optional",
			direction="Input")

		in_third_property.filter.type = "ValueList"
		in_third_property.filter.list = []
		in_third_property.enabled = False

		# Choose the fourth degree property direction which links to a locations, "ORIGIN" means in_wikiplace_IRI are origins, "DESTINATION" means in_wikiplace_IRI are destinations
		in_fourth_property_dir = arcpy.Parameter(
			displayName="The fourth degree property direction",
			name="in_fourth_property_dir",
			datatype="GPString",
			parameterType="Optional",
			direction="Input")

		in_fourth_property_dir.filter.type = "ValueList"
		in_fourth_property_dir.filter.list = ["BOTH", "ORIGIN", "DESTINATION"]
		in_fourth_property_dir.enabled = False

		# Choose the fourth degree property which links to a locations
		in_fourth_property = arcpy.Parameter(
			displayName="The fourth degree property",
			name="in_fourth_property",
			datatype="GPString",
			parameterType="Optional",
			direction="Input")

		in_fourth_property.filter.type = "ValueList"
		in_fourth_property.filter.list = []
		in_fourth_property.enabled = False

		out_location = arcpy.Parameter(
			displayName="Output Location",
			name="out_location",
			datatype="DEWorkspace",
			parameterType="Required",
			direction="Input")

		out_location.value = os.path.dirname(__file__)

		# Derived Output Triple Store Table Name
		out_table_name = arcpy.Parameter(
			displayName="Output Triple Store Table Name",
			name="out_table_name",
			datatype="GPString",
			parameterType="Required",
			direction="Input")

		# Derived Output Feature Class Name
		out_points_name = arcpy.Parameter(
			displayName="Output Feature Class Name",
			name="out_points_name",
			datatype="GPString",
			parameterType="Required",
			direction="Input")

		params = [in_wikiplace_IRI, in_relation_degree, in_first_property_dir, in_first_property, in_second_property_dir, in_second_property, in_third_property_dir, in_third_property, in_fourth_property_dir, in_fourth_property, out_location, out_table_name, out_points_name]

		return params



	def isLicensed(self):
		"""Set whether tool is licensed to execute."""
		return True

	def updateParameters(self, parameters):
		"""Modify the values and properties of parameters before internal
		validation is performed.  This method is called whenever a parameter
		has been changed."""
		in_wikiplace_IRI = parameters[0]
		in_relation_degree = parameters[1]
		in_first_property_dir = parameters[2]
		in_first_property = parameters[3]
		in_second_property_dir = parameters[4]
		in_second_property = parameters[5]
		in_third_property_dir = parameters[6]
		in_third_property = parameters[7]
		in_fourth_property_dir = parameters[8]
		in_fourth_property = parameters[9]
		out_location = parameters[10]
		out_table_name = parameters[11]
		out_points_name = parameters[12]

		

		if in_relation_degree.altered:
			relationDegree = int(in_relation_degree.valueAsText)
			if relationDegree == 1:
				in_first_property.enabled = True
				in_first_property_dir.enabled = True
				in_second_property.enabled = False
				in_second_property_dir.enabled = False
				in_third_property.enabled = False
				in_third_property_dir.enabled = False
				in_fourth_property.enabled = False
				in_fourth_property_dir.enabled = False
			elif relationDegree == 2:
				in_first_property.enabled = True
				in_first_property_dir.enabled = True
				in_second_property.enabled = True
				in_second_property_dir.enabled = True
				in_third_property.enabled = False
				in_third_property_dir.enabled = False
				in_fourth_property.enabled = False
				in_fourth_property_dir.enabled = False
			elif relationDegree == 3:
				in_first_property.enabled = True
				in_first_property_dir.enabled = True
				in_second_property.enabled = True
				in_second_property_dir.enabled = True
				in_third_property.enabled = True
				in_third_property_dir.enabled = True
				in_fourth_property.enabled = False
				in_fourth_property_dir.enabled = False
			elif relationDegree == 4:
				in_first_property.enabled = True
				in_first_property_dir.enabled = True
				in_second_property.enabled = True
				in_second_property_dir.enabled = True
				in_third_property.enabled = True
				in_third_property_dir.enabled = True
				in_fourth_property.enabled = True
				in_fourth_property_dir.enabled = True
		
			if in_wikiplace_IRI.value:
				inputFeatureClassName = in_wikiplace_IRI.valueAsText
				lastIndexOFGDB = inputFeatureClassName.rfind("\\")
				featureClassName = inputFeatureClassName[(lastIndexOFGDB+1):]
				currentWorkspace = inputFeatureClassName[:lastIndexOFGDB]

				arcpy.env.workspace = currentWorkspace
				out_location.value = currentWorkspace

				out_table_name.value = featureClassName + "PathQueryTripleStore"

				out_points_name.value = featureClassName + "PathQueryLocation"


				outLocation = out_location.valueAsText
				outTableName = out_table_name.valueAsText
				outputTableName = os.path.join(outLocation,outTableName)
				if arcpy.Exists(outputTableName):
					arcpy.AddError("The output table already exists in current workspace!")
					raise arcpy.ExecuteError

				outFeatureClassName = out_points_name.valueAsText
				outputFeatureClassName = os.path.join(outLocation,outFeatureClassName)
				if arcpy.Exists(outputFeatureClassName):
					arcpy.AddError("The output Feature Class already exists in current workspace!")
					raise arcpy.ExecuteError


				# get all the IRI from input point feature class of wikidata places
				inplaceIRIList = []
				cursor = arcpy.SearchCursor(inputFeatureClassName)
				for row in cursor:
					inplaceIRIList.append(row.getValue("URL"))



				# get the first property URL list and label list
				if in_first_property_dir.value:
					fristDirection = in_first_property_dir.valueAsText
					# get the first property URL list
					firstPropertyURLListJsonBindingObject = SPARQLQuery.relFinderCommonPropertyQuery(inplaceIRIList, relationDegree, [fristDirection], ["", "", ""])
					firstPropertyURLList = []
					for jsonItem in firstPropertyURLListJsonBindingObject:
						firstPropertyURLList.append(jsonItem["p1"]["value"])

					firstPropertyLabelJSON = SPARQLQuery.locationCommonPropertyLabelQuery(firstPropertyURLList)
					# firstPropertyLabelJSON = firstPropertyLabelJSONObj["results"]["bindings"]

					# get the first property label list
					firstPropertyURLList = []
					firstPropertyLabelList = []
					for jsonItem in firstPropertyLabelJSON:
						propertyURL = jsonItem["p"]["value"]
						firstPropertyURLList.append(propertyURL)
						propertyName = jsonItem["propertyLabel"]["value"]
						firstPropertyLabelList.append(propertyName)

					RelFinder.firstPropertyLabelURLDict = dict(zip(firstPropertyLabelList, firstPropertyURLList))

					in_first_property.filter.list = firstPropertyLabelList

					# get the second property URL list and label list
					if in_second_property_dir.value:
						fristDirection = in_first_property_dir.valueAsText
						firstProperty = in_first_property.valueAsText

						if firstProperty == None:
							firstProperty = ""
						else:
							firstProperty = RelFinder.firstPropertyLabelURLDict[firstProperty]

						secondDirection = in_second_property_dir.valueAsText
						
						# get the second property URL list
						secondPropertyURLListJsonBindingObject = SPARQLQuery.relFinderCommonPropertyQuery(inplaceIRIList, relationDegree, [fristDirection, secondDirection], [firstProperty, "", ""])
						secondPropertyURLList = []
						for jsonItem in secondPropertyURLListJsonBindingObject:
							secondPropertyURLList.append(jsonItem["p2"]["value"])

						secondPropertyLabelJSON = SPARQLQuery.locationCommonPropertyLabelQuery(secondPropertyURLList)
						# secondPropertyLabelJSON = secondPropertyLabelJSONObj["results"]["bindings"]

						# get the second property label list
						secondPropertyURLList = []
						secondPropertyLabelList = []
						for jsonItem in secondPropertyLabelJSON:
							propertyURL = jsonItem["p"]["value"]
							secondPropertyURLList.append(propertyURL)
							propertyName = jsonItem["propertyLabel"]["value"]
							secondPropertyLabelList.append(propertyName)

						RelFinder.secondPropertyLabelURLDict = dict(zip(secondPropertyLabelList, secondPropertyURLList))

						in_second_property.filter.list = secondPropertyLabelList

						# get the third property URL list and label list
						if in_third_property_dir.value:
							fristDirection = in_first_property_dir.valueAsText
							firstProperty = in_first_property.valueAsText

							secondDirection = in_second_property_dir.valueAsText
							secondProperty = in_second_property.valueAsText

							if firstProperty == None:
								firstProperty = ""
							else:
								firstProperty = RelFinder.firstPropertyLabelURLDict[firstProperty]
							if secondProperty == None:
								secondProperty = ""
							else:
								secondProperty = RelFinder.secondPropertyLabelURLDict[secondProperty]

							thirdDirection = in_third_property_dir.valueAsText
							
							# get the third property URL list
							thirdPropertyURLListJsonBindingObject = SPARQLQuery.relFinderCommonPropertyQuery(inplaceIRIList, relationDegree, [fristDirection, secondDirection, thirdDirection], [firstProperty, secondProperty, ""])
							thirdPropertyURLList = []
							for jsonItem in thirdPropertyURLListJsonBindingObject:
								thirdPropertyURLList.append(jsonItem["p3"]["value"])

							thirdPropertyLabelJSON = SPARQLQuery.locationCommonPropertyLabelQuery(thirdPropertyURLList)
							# thirdPropertyLabelJSON = thirdPropertyLabelJSONObj["results"]["bindings"]

							# get the third property label list
							thirdPropertyURLList = []
							thirdPropertyLabelList = []
							for jsonItem in thirdPropertyLabelJSON:
								propertyURL = jsonItem["p"]["value"]
								thirdPropertyURLList.append(propertyURL)
								propertyName = jsonItem["propertyLabel"]["value"]
								thirdPropertyLabelList.append(propertyName)

							RelFinder.thirdPropertyLabelURLDict = dict(zip(thirdPropertyLabelList, thirdPropertyURLList))

							in_third_property.filter.list = thirdPropertyLabelList

							# get the fourth property URL list and label list
							if in_fourth_property_dir.value:
								fristDirection = in_first_property_dir.valueAsText
								firstProperty = in_first_property.valueAsText

								secondDirection = in_second_property_dir.valueAsText
								secondProperty = in_second_property.valueAsText

								thirdDirection = in_third_property_dir.valueAsText
								thirdProperty = in_third_property.valueAsText

								if firstProperty == None:
									firstProperty = ""
								else:
									firstProperty = RelFinder.firstPropertyLabelURLDict[firstProperty]
								if secondProperty == None:
									secondProperty = ""
								else:
									secondProperty = RelFinder.secondPropertyLabelURLDict[secondProperty]
								if thirdProperty == None:
									thirdProperty = ""
								else:
									thirdProperty = RelFinder.thirdPropertyLabelURLDict[thirdProperty]

								fourthDirection = in_fourth_property_dir.valueAsText
								
								# get the fourth property URL list
								fourthPropertyURLListJsonBindingObject = SPARQLQuery.relFinderCommonPropertyQuery(inplaceIRIList, relationDegree, [fristDirection, secondDirection, thirdDirection, fourthDirection], [firstProperty, secondProperty, thirdProperty])
								fourthPropertyURLList = []
								for jsonItem in fourthPropertyURLListJsonBindingObject:
									fourthPropertyURLList.append(jsonItem["p4"]["value"])

								fourthPropertyLabelJSON = SPARQLQuery.locationCommonPropertyLabelQuery(fourthPropertyURLList)
								# fourthPropertyLabelJSON = fourthPropertyLabelJSONObj["results"]["bindings"]

								# get the fourth property label list
								fourthPropertyURLList = []
								fourthPropertyLabelList = []
								for jsonItem in fourthPropertyLabelJSON:
									propertyURL = jsonItem["p"]["value"]
									fourthPropertyURLList.append(propertyURL)
									propertyName = jsonItem["propertyLabel"]["value"]
									fourthPropertyLabelList.append(propertyName)

								RelFinder.fourthPropertyLabelURLDict = dict(zip(fourthPropertyLabelList, fourthPropertyURLList))

								in_fourth_property.filter.list = fourthPropertyLabelList


		return

	def updateMessages(self, parameters):
		"""Modify the messages created by internal validation for each tool
		parameter.  This method is called after internal validation."""
		return

	def execute(self, parameters, messages):
		"""The source code of the tool."""
		in_wikiplace_IRI = parameters[0]
		in_relation_degree = parameters[1]
		in_first_property_dir = parameters[2]
		in_first_property = parameters[3]
		in_second_property_dir = parameters[4]
		in_second_property = parameters[5]
		in_third_property_dir = parameters[6]
		in_third_property = parameters[7]
		in_fourth_property_dir = parameters[8]
		in_fourth_property = parameters[9]
		out_location = parameters[10]
		out_table_name = parameters[11]
		out_points_name = parameters[12]
		
		if in_wikiplace_IRI.value:
			inputFeatureClassName = in_wikiplace_IRI.valueAsText
			relationDegree = int(in_relation_degree.valueAsText)
			outLocation = out_location.valueAsText
			outTableName = out_table_name.valueAsText
			outFeatureClassName = out_points_name.valueAsText
			outputTableName = os.path.join(outLocation,outTableName)
			outputFeatureClassName = os.path.join(outLocation,outFeatureClassName)
			
			
			lastIndexOFGDB = inputFeatureClassName.rfind("\\")
			originFeatureClassName = inputFeatureClassName[(lastIndexOFGDB+1):]

			if outLocation.endswith(".gdb") == False:
				messages.addErrorMessage("Please enter a file geodatabase as the file location for output feature class.")
				raise arcpy.ExecuteError
			else:
				arcpy.env.workspace = outLocation

				
				if arcpy.Exists(outputTableName) or arcpy.Exists(outputFeatureClassName):
					messages.addErrorMessage("The output table or feature class already exists in current workspace!")
					raise arcpy.ExecuteError
				else:

					# get all the IRI from input point feature class of wikidata places
					inplaceIRIList = []
					cursor = arcpy.SearchCursor(inputFeatureClassName)
					for row in cursor:
						inplaceIRIList.append(row.getValue("URL"))

					# get the user specified property URL and direction at each degree
					propertyDirectionList = []
					selectPropertyURLList = ["", "", "", ""]
					if in_first_property_dir.value:
						fristDirection = in_first_property_dir.valueAsText
						firstProperty = in_first_property.valueAsText
						if firstProperty == None:
							firstPropertyURL = ""
						else:
							firstPropertyURL = RelFinder.firstPropertyLabelURLDict[firstProperty]

						propertyDirectionList.append(fristDirection)
						selectPropertyURLList[0] = firstPropertyURL


					if in_second_property_dir.value:
						secondDirection = in_second_property_dir.valueAsText
						secondProperty = in_second_property.valueAsText
						if secondProperty == None:
							secondPropertyURL = ""
						else:
							secondPropertyURL = RelFinder.secondPropertyLabelURLDict[secondProperty]

						propertyDirectionList.append(secondDirection)
						selectPropertyURLList[1] = secondPropertyURL

					if in_third_property_dir.value:
						thirdDirection = in_third_property_dir.valueAsText
						thirdProperty = in_third_property.valueAsText
						if thirdProperty == None:
							thirdPropertyURL = ""
						else:
							thirdPropertyURL = RelFinder.thirdPropertyLabelURLDict[thirdProperty]

						propertyDirectionList.append(thirdDirection)
						selectPropertyURLList[2] = thirdPropertyURL

					if in_fourth_property_dir.value:
						fourthDirection = in_fourth_property_dir.valueAsText
						fourthProperty = in_fourth_property.valueAsText
						if fourthProperty == None:
							fourthPropertyURL = ""
						else:
							fourthPropertyURL = RelFinder.thirdPropertyLabelURLDict[fourthProperty]

						propertyDirectionList.append(fourthDirection)
						selectPropertyURLList[3] = fourthPropertyURL

					arcpy.AddMessage("propertyDirectionList: {0}".format(propertyDirectionList))
					arcpy.AddMessage("selectPropertyURLList: {0}".format(selectPropertyURLList))

					# for the direction list, change "BOTH" to "OROIGIN" and "DESTINATION"
					directionExpendedLists = UTIL.directionListFromBoth2OD(propertyDirectionList)
					tripleStore = dict()
					for currentDirectionList in directionExpendedLists:
						# get a list of triples for curent specified property path
						newTripleStore = SPARQLQuery.relFinderTripleQuery(inplaceIRIList, currentDirectionList, selectPropertyURLList)
						
						tripleStore = UTIL.mergeTripleStoreDicts(tripleStore, newTripleStore)
						# tripleStore = UTIL.mergeListsWithUniqueElement(tripleStore, newTripleStore)

					triplePropertyURLList = []
					for triple in tripleStore:
						if triple.p not in triplePropertyURLList:
							triplePropertyURLList.append(triple.p)

					triplePropertyLabelJSON = SPARQLQuery.locationCommonPropertyLabelQuery(triplePropertyURLList)

					triplePropertyURLList = []
					triplePropertyLabelList = []
					for jsonItem in triplePropertyLabelJSON:
						propertyURL = jsonItem["p"]["value"]
						triplePropertyURLList.append(propertyURL)
						propertyName = jsonItem["propertyLabel"]["value"]
						triplePropertyLabelList.append(propertyName)

					triplePropertyURLLabelDict = dict(zip(triplePropertyURLList, triplePropertyLabelList))

					tripleStoreTable = arcpy.CreateTable_management(outLocation,outTableName)
					arcpy.AddField_management(tripleStoreTable, "Subject", "TEXT", field_length=50)
					arcpy.AddField_management(tripleStoreTable, "Predicate", "TEXT", field_length=50)
					arcpy.AddField_management(tripleStoreTable, "Object", "TEXT", field_length=50)
					arcpy.AddField_management(tripleStoreTable, "Pred_Label", "TEXT", field_length=50)
					arcpy.AddField_management(tripleStoreTable, "Degree", "LONG")


					# Create insert cursor for table
					rows = arcpy.InsertCursor(tripleStoreTable)

					
					# for triple in tripleStore:
					# 	row = rows.newRow()
					# 	row.setValue("Subject", triple[0])
					# 	row.setValue("Predicate", triple[1])
					# 	row.setValue("Object", triple[2])
					for triple in tripleStore:
						row = rows.newRow()
						row.setValue("Subject", triple.s)
						row.setValue("Predicate", triple.p)
						row.setValue("Object", triple.o)
						row.setValue("Pred_Label", triplePropertyURLLabelDict[triple.p])
						row.setValue("Degree", tripleStore[triple])

						rows.insertRow(row)

					entitySet = Set()
					for triple in tripleStore:
						entitySet.add(triple.s)
						entitySet.add(triple.o)
					# for triple in tripleStore:
					# 	entitySet.add(triple[0])
					# 	entitySet.add(triple[2])

					placeJSON = SPARQLQuery.endPlaceInformationQuery(list(entitySet))

					Json2Field.creatPlaceFeatureClassFromJSON(placeJSON, outputFeatureClassName, None, "")

					arcpy.env.workspace = outLocation

					originFeatureRelationshipClassName = outputFeatureClassName + "_" + outTableName + "_Origin" + "_RelClass"
					arcpy.CreateRelationshipClass_management(outputFeatureClassName, outTableName, originFeatureRelationshipClassName, "SIMPLE",
						"S-P-O Link", "Origin of S-P-O Link",
										 "FORWARD", "ONE_TO_MANY", "NONE", "URL", "Subject")

					endFeatureRelationshipClassName = outputFeatureClassName + "_" + outTableName + "_Destination" + "_RelClass"
					arcpy.CreateRelationshipClass_management(outputFeatureClassName, outTableName, endFeatureRelationshipClassName, "SIMPLE",
						"S-P-O Link", "Destination of S-P-O Link",
										 "FORWARD", "ONE_TO_MANY", "NONE", "URL", "Object")

					# Json2Field.getNoExistTableNameInWorkspace(outLocation,outTableName)

					LinkageTableName = Json2Field.getNoExistTableNameInWorkspace(outLocation,outTableName + "_Linkage")
					arcpy.CopyRows_management(outTableName, LinkageTableName)
					arcpy.JoinField_management(LinkageTableName, "Subject", outputFeatureClassName, "URL", [])
					arcpy.JoinField_management(LinkageTableName, "Object", outputFeatureClassName, "URL", [])

					
					# originFeatureClassName = LinkageTableName[(lastIndexOFGDB+1):]

					where_clause = '("URL" IS NOT NULL) AND ("URL_1" IS NOT NULL)'
					LinkedNotNullTableName = Json2Field.getNoExistTableNameInWorkspace(outLocation, LinkageTableName[(lastIndexOFGDB+1):] + "_SQL")
					arcpy.TableSelect_analysis(LinkageTableName, LinkedNotNullTableName, where_clause)

					lineFeatureName = Json2Field.getNoExistTableNameInWorkspace(outLocation, outTableName + "_LinkedLine")
					arcpy.XYToLine_management(LinkedNotNullTableName,lineFeatureName,
						"POINT_X","POINT_Y","POINT_X_1","POINT_Y_1","GREAT_CIRCLE")

					arcpy.JoinField_management(lineFeatureName, "OID", LinkedNotNullTableName, "OBJECTID", ["URL", "Label", "URL_1", "Label_1", "Pred_Label", "Degree"])


					mxd = arcpy.mapping.MapDocument("CURRENT")
					# get the data frame
					df = arcpy.mapping.ListDataFrames(mxd)[0]
					# create a new layer
					lineFeatureLayer = arcpy.mapping.Layer(os.path.join(outLocation,lineFeatureName))
					# add the layer to the map at the bottom of the TOC in data frame 0
					arcpy.mapping.AddLayer(df, lineFeatureLayer, "BOTTOM")







					# ["BOTH", "ORIGIN", "DESTINATION"]
					# if relationDegree > 1:
					# 	sencondDegreeTableAppendName = ""
					# 	if (propertyDirectionList[0] == "ORIGIN" or propertyDirectionList[0] == "BOTH") and (propertyDirectionList[1] == "ORIGIN" or propertyDirectionList[1] == "BOTH"):
							
					# 		if firstProperty == None:
					# 			sencondDegreeTableName += "_O"
					# 		else:
					# 			sencondDegreeTableName += "_O_" + firstProperty.replace(" ", "_")

					# 		if secondProperty == None:
					# 			sencondDegreeTableName += "_O"
					# 		else:
					# 			sencondDegreeTableName += "_O_" + secondProperty.replace(" ", "_")

					# 		sencondDegreeTableName = outTableName + sencondDegreeTableAppendName
					# 		arcpy.CopyRows_management(outTableName, sencondDegreeTableName)
					# 		arcpy.JoinField_management(sencondDegreeTableName, "Object", outTableName, "Subject", [])

					






					

					# # get the first property URL list and label list
					# if in_first_property_dir.value:
					# 	fristDirection = in_first_property_dir.valueAsText
					# 	# get the first property URL list
					# 	firstPropertyURLListJsonBindingObject = SPARQLQuery.relFinderCommonPropertyQuery(inplaceIRIList, 1, [fristDirection], ["", "", ""])
					# 	firstPropertyURLList = []
					# 	for jsonItem in firstPropertyURLListJsonBindingObject:
					# 		firstPropertyURLList.append(jsonItem["p1"]["value"])

					# 	firstPropertyLabelJSON = SPARQLQuery.locationCommonPropertyLabelQuery(firstPropertyURLList)
					# 	# firstPropertyLabelJSON = firstPropertyLabelJSONObj["results"]["bindings"]

					# 	# get the first property label list
					# 	firstPropertyURLList = []
					# 	firstPropertyLabelList = []
					# 	for jsonItem in firstPropertyLabelJSON:
					# 		propertyURL = jsonItem["p"]["value"]
					# 		firstPropertyURLList.append(propertyURL)
					# 		propertyName = jsonItem["propertyLabel"]["value"]
					# 		firstPropertyLabelList.append(propertyName)

					# 	# RelFinder.firstPropertyLabelURLDict = dict(zip(firstPropertyLabelList, firstPropertyURLList))

					# 	# in_first_property.filter.list = firstPropertyLabelList
					# 	arcpy.AddMessage("firstPropertyURLList: {0}".format(firstPropertyURLList))
					# 	arcpy.AddMessage("firstPropertyLabelList: {0}".format(firstPropertyLabelList))

					# 	# get the second property URL list and label list
					# 	if in_second_property_dir.value:
					# 		fristDirection = in_first_property_dir.valueAsText
					# 		firstProperty = in_first_property.valueAsText

					# 		if firstProperty == None:
					# 			firstProperty = ""
					# 		else:
					# 			firstProperty = RelFinder.firstPropertyLabelURLDict[firstProperty]

					# 		secondDirection = in_second_property_dir.valueAsText

					# 		arcpy.AddMessage("firstProperty: {0}".format(firstProperty))
							
					# 		# get the second property URL list
					# 		secondPropertyURLListJsonBindingObject = SPARQLQuery.relFinderCommonPropertyQuery(inplaceIRIList, 2, [fristDirection, secondDirection], [firstProperty, "", ""])
					# 		secondPropertyURLList = []
					# 		for jsonItem in secondPropertyURLListJsonBindingObject:
					# 			secondPropertyURLList.append(jsonItem["p2"]["value"])

					# 		secondPropertyLabelJSON = SPARQLQuery.locationCommonPropertyLabelQuery(secondPropertyURLList)
					# 		# secondPropertyLabelJSON = secondPropertyLabelJSONObj["results"]["bindings"]

					# 		# get the second property label list
					# 		secondPropertyURLList = []
					# 		secondPropertyLabelList = []
					# 		for jsonItem in secondPropertyLabelJSON:
					# 			propertyURL = jsonItem["p"]["value"]
					# 			secondPropertyURLList.append(propertyURL)
					# 			propertyName = jsonItem["propertyLabel"]["value"]
					# 			secondPropertyLabelList.append(propertyName)

					# 		# RelFinder.secondPropertyLabelURLDict = dict(zip(secondPropertyLabelList, secondPropertyURLList))

					# 		# in_second_property.filter.list = secondPropertyLabelList

					# 		arcpy.AddMessage("secondPropertyURLList: {0}".format(secondPropertyURLList))
					# 		arcpy.AddMessage("secondPropertyLabelList: {0}".format(secondPropertyLabelList))

					# 		# get the third property URL list and label list
					# 		if in_third_property_dir.value:
					# 			fristDirection = in_first_property_dir.valueAsText
					# 			firstProperty = in_first_property.valueAsText

					# 			secondDirection = in_second_property_dir.valueAsText
					# 			secondProperty = in_second_property.valueAsText

					# 			thirdDirection = in_third_property_dir.valueAsText

					# 			if firstProperty == None:
					# 				firstProperty = ""
					# 			else:
					# 				firstProperty = RelFinder.firstPropertyLabelURLDict[firstProperty]
					# 			if secondProperty == None:
					# 				secondProperty = ""
					# 			else:
					# 				secondProperty = RelFinder.secondPropertyLabelURLDict[secondProperty]

								
							
					# 			# get the third property URL list
					# 			thirdPropertyURLListJsonBindingObject = SPARQLQuery.relFinderCommonPropertyQuery(inplaceIRIList, 3, [fristDirection, secondDirection, thirdDirection], [firstProperty, secondProperty, ""])
					# 			thirdPropertyURLList = []
					# 			for jsonItem in thirdPropertyURLListJsonBindingObject:
					# 				thirdPropertyURLList.append(jsonItem["p3"]["value"])

					# 			thirdPropertyLabelJSON = SPARQLQuery.locationCommonPropertyLabelQuery(thirdPropertyURLList)
					# 			# thirdPropertyLabelJSON = thirdPropertyLabelJSONObj["results"]["bindings"]

					# 			# get the third property label list
					# 			thirdPropertyURLList = []
					# 			thirdPropertyLabelList = []
					# 			for jsonItem in thirdPropertyLabelJSON:
					# 				propertyURL = jsonItem["p"]["value"]
					# 				thirdPropertyURLList.append(propertyURL)
					# 				propertyName = jsonItem["propertyLabel"]["value"]
					# 				thirdPropertyLabelList.append(propertyName)

					# 			# RelFinder.thirdPropertyLabelURLDict = dict(zip(thirdPropertyLabelList, thirdPropertyURLList))

					# 			# in_third_property.filter.list = thirdPropertyLabelList

					# 			arcpy.AddMessage("thirdPropertyURLList: {0}".format(thirdPropertyURLList))
					# 			arcpy.AddMessage("thirdPropertyLabelList: {0}".format(thirdPropertyLabelList))

					# 			# get the fourth property URL list and label list
					# 			if in_fourth_property_dir.value:
					# 				fristDirection = in_first_property_dir.valueAsText
					# 				firstProperty = in_first_property.valueAsText

					# 				secondDirection = in_second_property_dir.valueAsText
					# 				secondProperty = in_second_property.valueAsText

					# 				thirdDirection = in_third_property_dir.valueAsText
					# 				thirdProperty = in_third_property.valueAsText

					# 				fourthDirection = in_fourth_property_dir.valueAsText

					# 				if firstProperty == None:
					# 					firstProperty = ""
					# 				else:
					# 					firstProperty = RelFinder.firstPropertyLabelURLDict[firstProperty]
					# 				if secondProperty == None:
					# 					secondProperty = ""
					# 				else:
					# 					secondProperty = RelFinder.secondPropertyLabelURLDict[secondProperty]
					# 				if thirdProperty == None:
					# 					thirdProperty = ""
					# 				else:
					# 					thirdProperty = RelFinder.thirdPropertyLabelURLDict[thirdProperty]

									
					# 				# get the fourth property URL list
					# 				fourthPropertyURLListJsonBindingObject = SPARQLQuery.relFinderCommonPropertyQuery(inplaceIRIList, 4, [fristDirection, secondDirection, thirdDirection, fourthDirection], [firstProperty, secondProperty, thirdProperty])
					# 				fourthPropertyURLList = []
					# 				for jsonItem in fourthPropertyURLListJsonBindingObject:
					# 					fourthPropertyURLList.append(jsonItem["p4"]["value"])

					# 				fourthPropertyLabelJSON = SPARQLQuery.locationCommonPropertyLabelQuery(fourthPropertyURLList)
					# 				# fourthPropertyLabelJSON = fourthPropertyLabelJSONObj["results"]["bindings"]

					# 				# get the fourth property label list
					# 				fourthPropertyURLList = []
					# 				fourthPropertyLabelList = []
					# 				for jsonItem in fourthPropertyLabelJSON:
					# 					propertyURL = jsonItem["p"]["value"]
					# 					fourthPropertyURLList.append(propertyURL)
					# 					propertyName = jsonItem["propertyLabel"]["value"]
					# 					fourthPropertyLabelList.append(propertyName)

					# 				# RelFinder.fourthPropertyLabelURLDict = dict(zip(fourthPropertyLabelList, fourthPropertyURLList))

					# 				# in_fourth_property.filter.list = fourthPropertyLabelList
					# 				arcpy.AddMessage("fourthPropertyURLList: {0}".format(fourthPropertyURLList))
					# 				arcpy.AddMessage("fourthPropertyLabelList: {0}".format(fourthPropertyLabelList))

					
					


					# if relationDegree > 4:
					# 	relationDegree = 4
					# 	in_relation_degree.value = 4
					
					# locationCommonPropertyURL = LocationPropertyPath.locationCommonPropertyDict[locationCommonPropertyNameCount]
					# locationLinkageRelationJSONObj = SPARQLQuery.locationLinkageRelationQuery(inplaceIRIList, locationCommonPropertyURL, relationDegree)
					# locationLinkageRelationJSON = locationLinkageRelationJSONObj["results"]["bindings"]

					# endPlaceIRISet = Set()
					# for jsonItem in locationLinkageRelationJSON:
					# 	endPlaceIRISet.add(jsonItem["end"]["value"])

					# endPlaceIRIList = list(endPlaceIRISet)

					# # endPlaceJSONObj = SPARQLQuery.endPlaceInformationQuery(endPlaceIRIList)
					
					# endPlaceJSON = SPARQLQuery.endPlaceInformationQuery(endPlaceIRIList)

					# Json2Field.creatPlaceFeatureClassFromJSON(endPlaceJSON, endFeatureClassName, None, "")


					# lastIndex = locationCommonPropertyNameCount.rfind("(")
					# locationCommonPropertyName = locationCommonPropertyNameCount[:lastIndex]
					# locationLinkageTableName = Json2Field.createLocationLinkageMappingTableFromJSON(locationLinkageRelationJSON, "origin", "end", inputFeatureClassName, endFeatureClassName, locationCommonPropertyURL, locationCommonPropertyName, relationDegree)

					# endFeatureRelationshipClassName = outFeatureClassName + "_" + locationLinkageTableName + "_RelClass"
					# arcpy.CreateRelationshipClass_management(outFeatureClassName, locationLinkageTableName, endFeatureRelationshipClassName, "SIMPLE",
					# 	"is "+ locationCommonPropertyName + "of", locationCommonPropertyName,
					# 					 "FORWARD", "ONE_TO_MANY", "NONE", "URL", "end")

					# originFeatureRelationshipClassName = originFeatureClassName + "_" + locationLinkageTableName + "_RelClass"
					# arcpy.CreateRelationshipClass_management(originFeatureClassName, locationLinkageTableName, originFeatureRelationshipClassName, "SIMPLE",
					# 	locationCommonPropertyName, "is "+ locationCommonPropertyName + "of",
					# 					 "FORWARD", "ONE_TO_MANY", "NONE", "URL", "origin")
				
		

		return





class SPARQLQuery(object):
	@staticmethod
	def endPlaceInformationQuery(endPlaceIRIList):
		jsonBindingObject = []
		i = 0
		while i < len(endPlaceIRIList):
			if i + 50 > len(endPlaceIRIList):
				endPlaceIRISubList = endPlaceIRIList[i:]
			else:
				endPlaceIRISubList = endPlaceIRIList[i:(i+50)]
			
			queryPrefix = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
							PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
							PREFIX owl: <http://www.w3.org/2002/07/owl#>
							PREFIX geo-pos: <http://www.w3.org/2003/01/geo/wgs84_pos#>
							PREFIX omgeo: <http://www.ontotext.com/owlim/geo#>
							PREFIX dbpedia: <http://dbpedia.org/resource/>
							PREFIX dbp-ont: <http://dbpedia.org/ontology/>
							PREFIX ff: <http://factforge.net/>
							PREFIX om: <http://www.ontotext.com/owlim/>
							PREFIX wikibase: <http://wikiba.se/ontology#>
							PREFIX bd: <http://www.bigdata.com/rdf#>
							PREFIX wdt: <http://www.wikidata.org/prop/direct/>
							PREFIX geo: <http://www.opengis.net/ont/geosparql#>"""

			endPlaceQuery = queryPrefix + """SELECT distinct ?place ?placeLabel ?location
							WHERE {
							?place wdt:P625 ?location .
							# retrieve the English label
							SERVICE wikibase:label {bd:serviceParam wikibase:language "en". ?place rdfs:label ?placeLabel .}
							?place wdt:P31 ?placeFlatType.
							?placeFlatType wdt:P279* wd:Q2221906.

							VALUES ?place
							{"""
			for IRI in endPlaceIRISubList:
				endPlaceQuery = endPlaceQuery + "<" + IRI + "> \n"

			endPlaceQuery = endPlaceQuery + """
							}
							}
							"""

			
			endPlaceSparqlParam = {'query': endPlaceQuery, 'format': 'json'}
			endPlaceSparqlRequest = requests.get('https://query.wikidata.org/sparql', params=endPlaceSparqlParam)
			arcpy.AddMessage("SPARQL: {0}".format(endPlaceSparqlRequest.url))
			jsonBindingObject.extend(endPlaceSparqlRequest.json()["results"]["bindings"])

			i = i + 50

		return jsonBindingObject


	@staticmethod
	def locationLinkageRelationQuery(inplaceIRIList, locationCommonPropertyURL, relationDegree):
		queryPrefix = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
						PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
						PREFIX wdt: <http://www.wikidata.org/prop/direct/>
						PREFIX owl: <http://www.w3.org/2002/07/owl#>
						PREFIX wikibase: <http://wikiba.se/ontology#>"""

		locationLinkageQuery = queryPrefix + """select ?origin ?end
						where
						{
						?origin """
		for i in range(relationDegree-1):
			locationLinkageQuery += """<""" + locationCommonPropertyURL + """>/"""


		locationLinkageQuery += """<""" + locationCommonPropertyURL + """>""" + """?end.

						VALUES ?origin
						{"""
		for IRI in inplaceIRIList:
			locationLinkageQuery = locationLinkageQuery + "<" + IRI + "> \n"

		locationLinkageQuery = locationLinkageQuery + """
						}
						}
						"""

		
		locationLinkageSparqlParam = {'query': locationLinkageQuery, 'format': 'json'}
		locationLinkageSparqlRequest = requests.get('https://query.wikidata.org/sparql', params=locationLinkageSparqlParam)
		arcpy.AddMessage("SPARQL: {0}".format(locationLinkageSparqlRequest.url))
		return locationLinkageSparqlRequest.json()

	@staticmethod
	def locationCommonPropertyQuery(inplaceIRIList):
		queryPrefix = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
						PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
						PREFIX wdt: <http://www.wikidata.org/prop/direct/>
						PREFIX owl: <http://www.w3.org/2002/07/owl#>
						PREFIX wikibase: <http://wikiba.se/ontology#>"""

		commonPropertyQuery = queryPrefix + """select distinct ?p  (count(distinct ?s) as ?NumofSub)
						where
						{
						?s ?p ?objPlace.
						?objPlace wdt:P625 ?coordinate.
						#?objPlace wdt:P31 ?placeFlatType.
						#?placeFlatType wdt:P279* wd:Q2221906.
						VALUES ?s
						{"""
		for IRI in inplaceIRIList:
			commonPropertyQuery = commonPropertyQuery + "<" + IRI + "> \n"

		commonPropertyQuery = commonPropertyQuery + """
						}
						}
						group by ?p
						order by DESC(?NumofSub)
						"""

		
		commonPropertySparqlParam = {'query': commonPropertyQuery, 'format': 'json'}
		commonPropertySparqlRequest = requests.get('https://query.wikidata.org/sparql', params=commonPropertySparqlParam)
		# print(commonPropertySparqlRequest.url)
		arcpy.AddMessage("SPARQL: {0}".format(commonPropertySparqlRequest.url))
		# commonPropertyJSON = commonPropertySparqlRequest.json()["results"]["bindings"]
		return commonPropertySparqlRequest.json()

	@staticmethod
	def commonPropertyQuery(inplaceIRIList):
		queryPrefix = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
						PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
						PREFIX wdt: <http://www.wikidata.org/prop/direct/>
						PREFIX owl: <http://www.w3.org/2002/07/owl#>"""

		commonPropertyQuery = queryPrefix + """select distinct ?p (count(distinct ?s) as ?NumofSub)
										where
										{ ?s owl:sameAs ?wikidataSub.
										?s ?p ?o.
										VALUES ?wikidataSub
										{"""
		for IRI in inplaceIRIList:
			commonPropertyQuery = commonPropertyQuery + "<" + IRI + "> \n"

		commonPropertyQuery = commonPropertyQuery + """
										}
										}
										group by ?p
										order by DESC(?NumofSub)
										"""

		
		commonPropertySparqlParam = {'query': commonPropertyQuery, 'format': 'json'}
		commonPropertySparqlRequest = requests.get('https://dbpedia.org/sparql', params=commonPropertySparqlParam)
		# print(commonPropertySparqlRequest.url)
		arcpy.AddMessage("SPARQL: {0}".format(commonPropertySparqlRequest.url))

		return commonPropertySparqlRequest.json()


	@staticmethod
	def inverseCommonPropertyQuery(inplaceIRIList):
		queryPrefix = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
						PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
						PREFIX wdt: <http://www.wikidata.org/prop/direct/>
						PREFIX owl: <http://www.w3.org/2002/07/owl#>"""

		commonPropertyQuery = queryPrefix + """select distinct ?p (count(distinct ?s) as ?NumofSub)
										where
										{ ?s owl:sameAs ?wikidataSub.
										?o ?p ?s.
										VALUES ?wikidataSub
										{"""
		for IRI in inplaceIRIList:
			commonPropertyQuery = commonPropertyQuery + "<" + IRI + "> \n"

		commonPropertyQuery = commonPropertyQuery + """
										}
										}
										group by ?p
										order by DESC(?NumofSub)
										"""

		
		commonPropertySparqlParam = {'query': commonPropertyQuery, 'format': 'json'}
		commonPropertySparqlRequest = requests.get('https://dbpedia.org/sparql', params=commonPropertySparqlParam)
		# print(commonPropertySparqlRequest.url)
		arcpy.AddMessage("SPARQL: {0}".format(commonPropertySparqlRequest.url))

		return commonPropertySparqlRequest.json()


	@staticmethod
	def locationDBpediaExpandedCommonPropertyQuery(inplaceIRIList):
		queryPrefix = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
						PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
						PREFIX wdt: <http://www.wikidata.org/prop/direct/>
						PREFIX owl: <http://www.w3.org/2002/07/owl#>"""

		commonPropertyQuery = queryPrefix + """select distinct ?p (count(distinct ?subDivision) as ?NumofSub)
										where
										{ ?s owl:sameAs ?wikidataSub.
										?subDivision dbo:isPartOf+ ?s.
										?subDivision ?p ?o.
										VALUES ?wikidataSub
										{"""
		for IRI in inplaceIRIList:
			commonPropertyQuery = commonPropertyQuery + "<" + IRI + "> \n"

		commonPropertyQuery = commonPropertyQuery + """
										}
										}
										group by ?p
										order by DESC(?NumofSub)
										"""

		
		commonPropertySparqlParam = {'query': commonPropertyQuery, 'format': 'json'}
		commonPropertySparqlRequest = requests.get('https://dbpedia.org/sparql', params=commonPropertySparqlParam)
		# print(commonPropertySparqlRequest.url)
		arcpy.AddMessage("SPARQL: {0}".format(commonPropertySparqlRequest.url))
		return commonPropertySparqlRequest.json()

	@staticmethod
	def locationDBpediaInverseExpandedCommonPropertyQuery(inplaceIRIList):
		queryPrefix = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
						PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
						PREFIX wdt: <http://www.wikidata.org/prop/direct/>
						PREFIX owl: <http://www.w3.org/2002/07/owl#>"""

		commonPropertyQuery = queryPrefix + """select distinct ?p (count(distinct ?subDivision) as ?NumofSub)
										where
										{ ?s owl:sameAs ?wikidataSub.
										?subDivision dbo:isPartOf+ ?s.
										?o ?p ?subDivision.
										VALUES ?wikidataSub
										{"""
		for IRI in inplaceIRIList:
			commonPropertyQuery = commonPropertyQuery + "<" + IRI + "> \n"

		commonPropertyQuery = commonPropertyQuery + """
										}
										}
										group by ?p
										order by DESC(?NumofSub)
										"""

		
		commonPropertySparqlParam = {'query': commonPropertyQuery, 'format': 'json'}
		commonPropertySparqlRequest = requests.get('https://dbpedia.org/sparql', params=commonPropertySparqlParam)
		# print(commonPropertySparqlRequest.url)
		arcpy.AddMessage("SPARQL: {0}".format(commonPropertySparqlRequest.url))
		return commonPropertySparqlRequest.json()


	@staticmethod
	def locationCommonPropertyLabelQuery(locationCommonPropertyURLList):
		jsonBindingObject = []
		i = 0
		while i < len(locationCommonPropertyURLList):
			if i + 50 > len(locationCommonPropertyURLList):
				propertyIRISubList = locationCommonPropertyURLList[i:]
			else:
				propertyIRISubList = locationCommonPropertyURLList[i:(i+50)]

			queryPrefix = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
							PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
							PREFIX wdt: <http://www.wikidata.org/prop/direct/>
							PREFIX owl: <http://www.w3.org/2002/07/owl#>
							PREFIX wikibase: <http://wikiba.se/ontology#>"""

			commonPropertyLabelQuery = queryPrefix + """select ?p ?propertyLabel
							where
							{
							?wdProperty wikibase:directClaim ?p.
							SERVICE wikibase:label {bd:serviceParam wikibase:language "en". ?wdProperty rdfs:label ?propertyLabel.}
							VALUES ?p
							{"""
			for propertyURL in propertyIRISubList:
				commonPropertyLabelQuery = commonPropertyLabelQuery + "<" + propertyURL + "> \n"

			commonPropertyLabelQuery = commonPropertyLabelQuery + """
							}
							}
							"""

			
			commonPropertyLabelSparqlParam = {'query': commonPropertyLabelQuery, 'format': 'json'}
			commonPropertyLabelSparqlRequest = requests.get('https://query.wikidata.org/sparql', params=commonPropertyLabelSparqlParam)
			# print(commonPropertySparqlRequest.url)
			arcpy.AddMessage("SPARQL: {0}".format(commonPropertyLabelSparqlRequest.url))
			# commonPropertyJSON = commonPropertySparqlRequest.json()["results"]["bindings"]
			jsonBindingObject.extend(commonPropertyLabelSparqlRequest.json()["results"]["bindings"])

			i = i + 50
		return jsonBindingObject

	@staticmethod
	def functionalPropertyQuery(propertyURLList):
		# give a list of property, get a sublist which are functional property

		# send a SPARQL query to DBpedia endpoint to test whether the user selected properties are functionalProperty
		jsonBindingObject = []
		i = 0
		while i < len(propertyURLList):
			if i + 50 > len(propertyURLList):
				propertyURLSubList = propertyURLList[i:]
			else:
				propertyURLSubList = propertyURLList[i:(i+50)]

			queryPrefix = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
							PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
							PREFIX wdt: <http://www.wikidata.org/prop/direct/>
							PREFIX owl: <http://www.w3.org/2002/07/owl#>"""

			isFuncnalPropertyQuery = queryPrefix + """select ?property
							where
							{ ?property a owl:FunctionalProperty.
							VALUES ?property
							{"""
			for propertyURL in propertyURLSubList:
				isFuncnalPropertyQuery = isFuncnalPropertyQuery + "<" + propertyURL + "> \n"

			isFuncnalPropertyQuery = isFuncnalPropertyQuery + """
							}
							}
							"""

			
			isFuncnalPropertySparqlParam = {'query': isFuncnalPropertyQuery, 'format': 'json'}
			
			isFuncnalPropertySparqlRequest = requests.get('https://dbpedia.org/sparql', params=isFuncnalPropertySparqlParam)
			print(isFuncnalPropertySparqlRequest.url)
			arcpy.AddMessage("isFuncnalPropertySparqlRequest: {0}".format(isFuncnalPropertySparqlRequest.url))

			jsonBindingObject.extend(isFuncnalPropertySparqlRequest.json()["results"]["bindings"])

			i = i + 50
		return jsonBindingObject
		# return isFuncnalPropertySparqlRequest.json()

	@staticmethod
	def inverseFunctionalPropertyQuery(propertyURLList):
		# give a list of property, get a sublist which are inverse functional property

		# send a SPARQL query to DBpedia endpoint to test whether the user selected properties are InverseFunctionalProperty
		jsonBindingObject = []
		i = 0
		while i < len(propertyURLList):
			if i + 50 > len(propertyURLList):
				propertyURLSubList = propertyURLList[i:]
			else:
				propertyURLSubList = propertyURLList[i:(i+50)]

			queryPrefix = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
							PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
							PREFIX wdt: <http://www.wikidata.org/prop/direct/>
							PREFIX owl: <http://www.w3.org/2002/07/owl#>"""

			isFuncnalPropertyQuery = queryPrefix + """select ?property
							where
							{ ?property a owl:InverseFunctionalProperty.
							VALUES ?property
							{"""
			for propertyURL in propertyURLSubList:
				isFuncnalPropertyQuery = isFuncnalPropertyQuery + "<" + propertyURL + "> \n"

			isFuncnalPropertyQuery = isFuncnalPropertyQuery + """
							}
							}
							"""

			
			isFuncnalPropertySparqlParam = {'query': isFuncnalPropertyQuery, 'format': 'json'}
			
			isFuncnalPropertySparqlRequest = requests.get('https://dbpedia.org/sparql', params=isFuncnalPropertySparqlParam)
			print(isFuncnalPropertySparqlRequest.url)
			arcpy.AddMessage("isFuncnalPropertySparqlRequest: {0}".format(isFuncnalPropertySparqlRequest.url))

			jsonBindingObject.extend(isFuncnalPropertySparqlRequest.json()["results"]["bindings"])

			i = i + 50
		return jsonBindingObject

		# return isFuncnalPropertySparqlRequest.json()

	@staticmethod
	def dbpediaIRIQuery(inplaceIRIList):
		# send a SPARQL query to DBpedia endpoint to get the DBpedia IRI according to wikidata IRI
		# inplaceIRIList:  a list of wikidata IRI for locations in the Feature class
		queryPrefix = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
						PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
						PREFIX wdt: <http://www.wikidata.org/prop/direct/>
						PREFIX owl: <http://www.w3.org/2002/07/owl#>"""

		dbpediaIRIQuery = queryPrefix + """select ?DBpediaSub ?wikidataSub
						where
						{ ?DBpediaSub owl:sameAs ?wikidataSub.
						VALUES ?wikidataSub
						{
						"""
		for IRI in inplaceIRIList:
			dbpediaIRIQuery = dbpediaIRIQuery + "<" + IRI + "> \n"

		dbpediaIRIQuery = dbpediaIRIQuery + """
						}
						}
						"""

		
		dbpediaIRISparqlParam = {'query': dbpediaIRIQuery, 'format': 'json'}
		
		dbpediaIRISparqlRequest = requests.get('https://dbpedia.org/sparql', params=dbpediaIRISparqlParam)
		print(dbpediaIRISparqlRequest.url)
		arcpy.AddMessage("dbpediaIRISparqlRequest: {0}".format(dbpediaIRISparqlRequest.url))
		return dbpediaIRISparqlRequest.json()


	@staticmethod
	def propertyValueQuery(inplaceIRIList, propertyURL):
		# according to a list of wikidata IRI (inplaceIRIList), get the value for a specific property (propertyURL) from DBpedia
		jsonBindingObject = []
		i = 0
		while i < len(inplaceIRIList):
			if i + 50 > len(inplaceIRIList):
				inplaceIRISubList = inplaceIRIList[i:]
			else:
				inplaceIRISubList = inplaceIRIList[i:(i+50)]
			queryPrefix = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
							PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
							PREFIX wdt: <http://www.wikidata.org/prop/direct/>
							PREFIX owl: <http://www.w3.org/2002/07/owl#>"""

			PropertyValueQuery = queryPrefix + """select ?wikidataSub ?o
							where
							{ ?s owl:sameAs ?wikidataSub.
							?s <"""+ propertyURL +"""> ?o.
							VALUES ?wikidataSub
							{
							"""
			for IRI in inplaceIRISubList:
				PropertyValueQuery +=  "<" + IRI + "> \n"

			PropertyValueQuery += """
							}
							}
							"""

			
			PropertyValueSparqlParam = {'query': PropertyValueQuery, 'format': 'json'}
			
			PropertyValueSparqlRequest = requests.get('https://dbpedia.org/sparql', params=PropertyValueSparqlParam)
			print(PropertyValueSparqlRequest.url)
			arcpy.AddMessage("PropertyValueSparqlRequest: {0}".format(PropertyValueSparqlRequest.url))
			jsonBindingObject.extend(PropertyValueSparqlRequest.json()["results"]["bindings"])

			i = i + 50

		return jsonBindingObject
		# return PropertyValueSparqlRequest.json()

	@staticmethod
	def inversePropertyValueQuery(inplaceIRIList, propertyURL):
		# according to a list of wikidata IRI (inplaceIRIList), get the value for a specific property (propertyURL) from DBpedia
		jsonBindingObject = []
		i = 0
		while i < len(inplaceIRIList):
			if i + 50 > len(inplaceIRIList):
				inplaceIRISubList = inplaceIRIList[i:]
			else:
				inplaceIRISubList = inplaceIRIList[i:(i+50)]
			queryPrefix = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
							PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
							PREFIX wdt: <http://www.wikidata.org/prop/direct/>
							PREFIX owl: <http://www.w3.org/2002/07/owl#>"""

			PropertyValueQuery = queryPrefix + """select ?wikidataSub ?o
							where
							{ ?s owl:sameAs ?wikidataSub.
							?o <"""+ propertyURL +"""> ?s.
							VALUES ?wikidataSub
							{
							"""
			for IRI in inplaceIRISubList:
				PropertyValueQuery +=  "<" + IRI + "> \n"

			PropertyValueQuery += """
							}
							}
							"""

			
			PropertyValueSparqlParam = {'query': PropertyValueQuery, 'format': 'json'}
			
			PropertyValueSparqlRequest = requests.get('https://dbpedia.org/sparql', params=PropertyValueSparqlParam)
			print(PropertyValueSparqlRequest.url)
			arcpy.AddMessage("PropertyValueSparqlRequest: {0}".format(PropertyValueSparqlRequest.url))
			jsonBindingObject.extend(PropertyValueSparqlRequest.json()["results"]["bindings"])

			i = i + 50

		return jsonBindingObject

	@staticmethod
	def isPartOfReverseTransiveQuery(inplaceIRIList):
		# according to a list of wikidata IRI (inplaceIRIList), get the coresponding DBpedia IRI. 
		# Using "isPartOf" relation to get the subdivision of current DBpedia IRI locatoin 
		jsonBindingObject = []
		i = 0
		while i < len(inplaceIRIList):
			if i + 50 > len(inplaceIRIList):
				inplaceIRISubList = inplaceIRIList[i:]
			else:
				inplaceIRISubList = inplaceIRIList[i:(i+50)]
			queryPrefix = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
							PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
							PREFIX wdt: <http://www.wikidata.org/prop/direct/>
							PREFIX owl: <http://www.w3.org/2002/07/owl#>"""

			PropertyValueQuery = queryPrefix + """select ?wikidataSub ?subDivision
							where
							{ ?s owl:sameAs ?wikidataSub.
							?subDivision dbo:isPartOf+ ?s.
							VALUES ?wikidataSub
							{
							"""
			for IRI in inplaceIRISubList:

				PropertyValueQuery +=  "<" + IRI + "> \n"

			PropertyValueQuery += """
							}
							}
							"""

			
			PropertyValueSparqlParam = {'query': PropertyValueQuery, 'format': 'json'}
			
			PropertyValueSparqlRequest = requests.get('https://dbpedia.org/sparql', params=PropertyValueSparqlParam)
			print(PropertyValueSparqlRequest.url)
			arcpy.AddMessage("PropertyValueSparqlRequest: {0}".format(PropertyValueSparqlRequest.url))
			jsonBindingObject.extend(PropertyValueSparqlRequest.json()["results"]["bindings"])

			i = i + 50

		return jsonBindingObject


	@staticmethod
	def expandedPropertyValueQuery(inplaceIRIList, propertyURL):
		# according to a list of wikidata IRI (inplaceIRIList), get the coresponding DBpedia IRI. 
		# Using "isPartOf" relation to get the subdivision of current DBpedia IRI locatoin and then get the value for a specific property (propertyURL) from DBpedia
		
		jsonBindingObject = []
		i = 0
		while i < len(inplaceIRIList):
			if i + 50 > len(inplaceIRIList):
				inplaceIRISubList = inplaceIRIList[i:]
			else:
				inplaceIRISubList = inplaceIRIList[i:(i+50)]
			queryPrefix = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
							PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
							PREFIX wdt: <http://www.wikidata.org/prop/direct/>
							PREFIX owl: <http://www.w3.org/2002/07/owl#>"""

			PropertyValueQuery = queryPrefix + """select ?wikidataSub ?subDivision ?o
							where
							{ ?s owl:sameAs ?wikidataSub.
							?subDivision dbo:isPartOf+ ?s.
							?subDivision <"""+ propertyURL +"""> ?o.
							VALUES ?wikidataSub
							{
							"""
			for IRI in inplaceIRISubList:

				PropertyValueQuery +=  "<" + IRI + "> \n"

			PropertyValueQuery += """
							}
							}
							"""

			
			PropertyValueSparqlParam = {'query': PropertyValueQuery, 'format': 'json'}
			
			PropertyValueSparqlRequest = requests.get('https://dbpedia.org/sparql', params=PropertyValueSparqlParam)
			print(PropertyValueSparqlRequest.url)
			arcpy.AddMessage("PropertyValueSparqlRequest: {0}".format(PropertyValueSparqlRequest.url))
			jsonBindingObject.extend(PropertyValueSparqlRequest.json()["results"]["bindings"])

			i = i + 50

		return jsonBindingObject

		# return PropertyValueSparqlRequest.json()

	@staticmethod
	def inverseExpandedPropertyValueQuery(inplaceIRIList, propertyURL):
		# according to a list of wikidata IRI (inplaceIRIList), get the coresponding DBpedia IRI. 
		# Using "isPartOf" relation to get the subdivision of current DBpedia IRI locatoin and then get the value for a specific property (propertyURL) from DBpedia
		
		jsonBindingObject = []
		i = 0
		while i < len(inplaceIRIList):
			if i + 50 > len(inplaceIRIList):
				inplaceIRISubList = inplaceIRIList[i:]
			else:
				inplaceIRISubList = inplaceIRIList[i:(i+50)]
			queryPrefix = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
							PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
							PREFIX wdt: <http://www.wikidata.org/prop/direct/>
							PREFIX owl: <http://www.w3.org/2002/07/owl#>"""

			PropertyValueQuery = queryPrefix + """select ?wikidataSub ?subDivision ?o
							where
							{ ?s owl:sameAs ?wikidataSub.
							?subDivision dbo:isPartOf+ ?s.
							?o <"""+ propertyURL +"""> ?subDivision.
							VALUES ?wikidataSub
							{
							"""
			for IRI in inplaceIRISubList:

				PropertyValueQuery +=  "<" + IRI + "> \n"

			PropertyValueQuery += """
							}
							}
							"""

			
			PropertyValueSparqlParam = {'query': PropertyValueQuery, 'format': 'json'}
			
			PropertyValueSparqlRequest = requests.get('https://dbpedia.org/sparql', params=PropertyValueSparqlParam)
			print(PropertyValueSparqlRequest.url)
			arcpy.AddMessage("PropertyValueSparqlRequest: {0}".format(PropertyValueSparqlRequest.url))
			jsonBindingObject.extend(PropertyValueSparqlRequest.json()["results"]["bindings"])

			i = i + 50

		return jsonBindingObject

	@staticmethod
	def relFinderCommonPropertyQuery(inplaceIRIList, relationDegree, propertyDirectionList, selectPropertyURLList):
		# get the property URL list in the specific degree path from the inplaceIRIList
		# inplaceIRIList: the URL list of wikidata locations
		# relationDegree: the degree of the property on the path the current query wants to get
		# propertyDirectionList: the list of property direction, it has at most 4 elements, the length is the path degree. The element value is from ["BOTH", "ORIGIN", "DESTINATION"]
		# selectPropertyURLList: the selected peoperty URL list, it always has three elements, "" if no property has been selected

		if len(propertyDirectionList) == 1:
			selectParam = "?p1"
		elif len(propertyDirectionList) == 2:
			selectParam = "?p2"
		elif len(propertyDirectionList) == 3:
			selectParam = "?p3"
		elif len(propertyDirectionList) == 4:
			selectParam = "?p4"

		jsonBindingObject = []
		i = 0
		while i < len(inplaceIRIList):
			if i + 50 > len(inplaceIRIList):
				inplaceIRISubList = inplaceIRIList[i:]
			else:
				inplaceIRISubList = inplaceIRIList[i:(i+50)]
			
			queryPrefix = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
							PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
							PREFIX owl: <http://www.w3.org/2002/07/owl#>
							PREFIX geo-pos: <http://www.w3.org/2003/01/geo/wgs84_pos#>
							PREFIX omgeo: <http://www.ontotext.com/owlim/geo#>
							PREFIX dbpedia: <http://dbpedia.org/resource/>
							PREFIX dbp-ont: <http://dbpedia.org/ontology/>
							PREFIX ff: <http://factforge.net/>
							PREFIX om: <http://www.ontotext.com/owlim/>
							PREFIX wikibase: <http://wikiba.se/ontology#>
							PREFIX bd: <http://www.bigdata.com/rdf#>
							PREFIX wdt: <http://www.wikidata.org/prop/direct/>
							PREFIX geo: <http://www.opengis.net/ont/geosparql#>"""

			

			# ["BOTH", "ORIGIN", "DESTINATION"]
			# if propertyDirectionList[0] == "BOTH"

			

			relFinderPropertyQuery = queryPrefix + """SELECT distinct """ + selectParam + """
							WHERE {"""

			if len(propertyDirectionList) > 0:
				if selectPropertyURLList[0] == "":
					if propertyDirectionList[0] == "BOTH":
						relFinderPropertyQuery += """{?place ?p1 ?o1.} UNION {?o1 ?p1 ?place.}\n"""
					elif propertyDirectionList[0] == "ORIGIN":
						relFinderPropertyQuery += """?place ?p1 ?o1.\n"""
					elif propertyDirectionList[0] == "DESTINATION":
						relFinderPropertyQuery += """?o1 ?p1 ?place.\n"""

					if relationDegree > 1:
						relFinderPropertyQuery += """?p1 a owl:ObjectProperty.\n"""
				else:
					if propertyDirectionList[0] == "BOTH":
						relFinderPropertyQuery += """{?place <"""+ selectPropertyURLList[0] + """> ?o1.} UNION {?o1 <"""+ selectPropertyURLList[0] + """> ?place.}\n"""
					elif propertyDirectionList[0] == "ORIGIN":
						relFinderPropertyQuery += """?place <"""+ selectPropertyURLList[0] + """> ?o1.\n"""
					elif propertyDirectionList[0] == "DESTINATION":
						relFinderPropertyQuery += """?o1 <"""+ selectPropertyURLList[0] + """> ?place.\n"""

			if len(propertyDirectionList) > 1:
				if selectPropertyURLList[1] == "":
					if propertyDirectionList[1] == "BOTH":
						relFinderPropertyQuery += """{?o1 ?p2 ?o2.} UNION {?o2 ?p2 ?o1.}\n"""
					elif propertyDirectionList[1] == "ORIGIN":
						relFinderPropertyQuery += """?o1 ?p2 ?o2.\n"""
					elif propertyDirectionList[1] == "DESTINATION":
						relFinderPropertyQuery += """?o2 ?p2 ?o1.\n"""

					if relationDegree > 2:
						relFinderPropertyQuery += """?p2 a owl:ObjectProperty.\n"""
				else:
					if propertyDirectionList[1] == "BOTH":
						relFinderPropertyQuery += """{?o1 <"""+ selectPropertyURLList[1] + """> ?o2.} UNION {?o2 <"""+ selectPropertyURLList[1] + """> ?o1.}\n"""
					elif propertyDirectionList[1] == "ORIGIN":
						relFinderPropertyQuery += """?o1 <"""+ selectPropertyURLList[1] + """> ?o2.\n"""
					elif propertyDirectionList[1] == "DESTINATION":
						relFinderPropertyQuery += """?o2 <"""+ selectPropertyURLList[1] + """> ?o1.\n"""

			if len(propertyDirectionList) > 2:
				if selectPropertyURLList[2] == "":
					if propertyDirectionList[2] == "BOTH":
						relFinderPropertyQuery += """{?o2 ?p3 ?o3.} UNION {?o3 ?p3 ?o2.}\n"""
					elif propertyDirectionList[2] == "ORIGIN":
						relFinderPropertyQuery += """?o2 ?p3 ?o3.\n"""
					elif propertyDirectionList[2] == "DESTINATION":
						relFinderPropertyQuery += """?o3 ?p3 ?o2.\n"""

					if relationDegree > 3:
						relFinderPropertyQuery += """?p3 a owl:ObjectProperty.\n"""
				else:
					if propertyDirectionList[2] == "BOTH":
						relFinderPropertyQuery += """{?o2 <"""+ selectPropertyURLList[2] + """> ?o3.} UNION {?o3 <"""+ selectPropertyURLList[2] + """> ?o2.}\n"""
					elif propertyDirectionList[2] == "ORIGIN":
						relFinderPropertyQuery += """?o2 <"""+ selectPropertyURLList[2] + """> ?o3.\n"""
					elif propertyDirectionList[2] == "DESTINATION":
						relFinderPropertyQuery += """?o3 <"""+ selectPropertyURLList[2] + """> ?o2.\n"""

			if len(propertyDirectionList) > 3:
				if propertyDirectionList[3] == "BOTH":
					relFinderPropertyQuery += """{?o3 ?p4 ?o4.} UNION {?o4 ?p4 ?o3.}\n"""
				elif propertyDirectionList[3] == "ORIGIN":
					relFinderPropertyQuery += """?o3 ?p4 ?o4.\n"""
				elif propertyDirectionList[3] == "DESTINATION":
					relFinderPropertyQuery += """?o4 ?p4 ?o3.\n"""

							

			relFinderPropertyQuery += """
							VALUES ?place
							{"""
			for IRI in inplaceIRISubList:
				relFinderPropertyQuery = relFinderPropertyQuery + "<" + IRI + "> \n"

			relFinderPropertyQuery = relFinderPropertyQuery + """
							}
							}
							"""

			
			relFinderPropertySparqlParam = {'query': relFinderPropertyQuery, 'format': 'json'}
			relFinderPropertySparqlRequest = requests.get('https://query.wikidata.org/sparql', params=relFinderPropertySparqlParam)
			arcpy.AddMessage("SPARQL: {0}".format(relFinderPropertySparqlRequest.url))
			jsonBindingObject.extend(relFinderPropertySparqlRequest.json()["results"]["bindings"])

			i = i + 50

		return jsonBindingObject




	@staticmethod
	def relFinderTripleQuery(inplaceIRIList, propertyDirectionList, selectPropertyURLList):
		# get the triple set in the specific degree path from the inplaceIRIList
		# inplaceIRIList: the URL list of wikidata locations
		# propertyDirectionList: the list of property direction, it has at most 4 elements, the length is the path degree. The element value is from ["ORIGIN", "DESTINATION"]
		# selectPropertyURLList: the selected peoperty URL list, it always has 4 elements, "" if no property has been selected

		# get the selected parameter 
		# selectParam = "?place ?p1 ?o1 ?p2 ?o2 ?p3 ?o3 ?p4 ?o4"

		selectParam = "?place "
		if len(propertyDirectionList) > 0:
			if selectPropertyURLList[0] == "":
				selectParam += "?p1 "

		selectParam += "?o1 "

		if len(propertyDirectionList) > 1:
			if selectPropertyURLList[1] == "":
				selectParam += "?p2 " 

		selectParam += "?o2 "

		if len(propertyDirectionList) > 2:
			if selectPropertyURLList[2] == "":
				selectParam += "?p3 " 

		selectParam += "?o3 "

		if len(propertyDirectionList) > 3:
			if selectPropertyURLList[3] == "":
				selectParam += "?p4 " 

		selectParam += "?o4 "

		jsonBindingObject = []
		i = 0
		while i < len(inplaceIRIList):
			if i + 50 > len(inplaceIRIList):
				inplaceIRISubList = inplaceIRIList[i:]
			else:
				inplaceIRISubList = inplaceIRIList[i:(i+50)]
			
			queryPrefix = """PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
							PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
							PREFIX owl: <http://www.w3.org/2002/07/owl#>
							PREFIX geo-pos: <http://www.w3.org/2003/01/geo/wgs84_pos#>
							PREFIX omgeo: <http://www.ontotext.com/owlim/geo#>
							PREFIX dbpedia: <http://dbpedia.org/resource/>
							PREFIX dbp-ont: <http://dbpedia.org/ontology/>
							PREFIX ff: <http://factforge.net/>
							PREFIX om: <http://www.ontotext.com/owlim/>
							PREFIX wikibase: <http://wikiba.se/ontology#>
							PREFIX bd: <http://www.bigdata.com/rdf#>
							PREFIX wdt: <http://www.wikidata.org/prop/direct/>
							PREFIX geo: <http://www.opengis.net/ont/geosparql#>"""


			relFinderPropertyQuery = queryPrefix + """SELECT distinct """ + selectParam + """
							WHERE {"""

			if len(propertyDirectionList) > 0:
				if selectPropertyURLList[0] == "":
					# if propertyDirectionList[0] == "BOTH":
					# 	relFinderPropertyQuery += """{?place ?p1 ?o1.} UNION {?o1 ?p1 ?place.}\n"""
					if propertyDirectionList[0] == "ORIGIN":
						relFinderPropertyQuery += """?place ?p1 ?o1.\n"""
					elif propertyDirectionList[0] == "DESTINATION":
						relFinderPropertyQuery += """?o1 ?p1 ?place.\n"""
				else:
					# if propertyDirectionList[0] == "BOTH":
					# 	relFinderPropertyQuery += """{?place <"""+ selectPropertyURLList[0] + """> ?o1.} UNION {?o1 <"""+ selectPropertyURLList[0] + """> ?place.}\n"""
					if propertyDirectionList[0] == "ORIGIN":
						relFinderPropertyQuery += """?place <"""+ selectPropertyURLList[0] + """> ?o1.\n"""
					elif propertyDirectionList[0] == "DESTINATION":
						relFinderPropertyQuery += """?o1 <"""+ selectPropertyURLList[0] + """> ?place.\n"""

			if len(propertyDirectionList) > 1:
				if selectPropertyURLList[1] == "":
					# if propertyDirectionList[1] == "BOTH":
					# 	relFinderPropertyQuery += """{?o1 ?p2 ?o2.} UNION {?o2 ?p2 ?o1.}\n"""
					if propertyDirectionList[1] == "ORIGIN":
						relFinderPropertyQuery += """?o1 ?p2 ?o2.\n"""
					elif propertyDirectionList[1] == "DESTINATION":
						relFinderPropertyQuery += """?o2 ?p2 ?o1.\n"""
				else:
					# if propertyDirectionList[1] == "BOTH":
					# 	relFinderPropertyQuery += """{?o1 <"""+ selectPropertyURLList[1] + """> ?o2.} UNION {?o2 <"""+ selectPropertyURLList[1] + """> ?o1.}\n"""
					if propertyDirectionList[1] == "ORIGIN":
						relFinderPropertyQuery += """?o1 <"""+ selectPropertyURLList[1] + """> ?o2.\n"""
					elif propertyDirectionList[1] == "DESTINATION":
						relFinderPropertyQuery += """?o2 <"""+ selectPropertyURLList[1] + """> ?o1.\n"""

			if len(propertyDirectionList) > 2:
				if selectPropertyURLList[2] == "":
					# if propertyDirectionList[2] == "BOTH":
					# 	relFinderPropertyQuery += """{?o2 ?p3 ?o3.} UNION {?o3 ?p3 ?o2.}\n"""
					if propertyDirectionList[2] == "ORIGIN":
						relFinderPropertyQuery += """?o2 ?p3 ?o3.\n"""
					elif propertyDirectionList[2] == "DESTINATION":
						relFinderPropertyQuery += """?o3 ?p3 ?o2.\n"""
				else:
					# if propertyDirectionList[2] == "BOTH":
					# 	relFinderPropertyQuery += """{?o2 <"""+ selectPropertyURLList[2] + """> ?o3.} UNION {?o3 <"""+ selectPropertyURLList[2] + """> ?o2.}\n"""
					if propertyDirectionList[2] == "ORIGIN":
						relFinderPropertyQuery += """?o2 <"""+ selectPropertyURLList[2] + """> ?o3.\n"""
					elif propertyDirectionList[2] == "DESTINATION":
						relFinderPropertyQuery += """?o3 <"""+ selectPropertyURLList[2] + """> ?o2.\n"""

			if len(propertyDirectionList) > 3:
				if selectPropertyURLList[3] == "":
					# if propertyDirectionList[3] == "BOTH":
					# 	relFinderPropertyQuery += """{?o3 ?p4 ?o4.} UNION {?o4 ?p4 ?o3.}\n"""
					if propertyDirectionList[3] == "ORIGIN":
						relFinderPropertyQuery += """?o3 ?p4 ?o4.\n"""
					elif propertyDirectionList[3] == "DESTINATION":
						relFinderPropertyQuery += """?o4 ?p4 ?o3.\n"""
				else:
					# if propertyDirectionList[3] == "BOTH":
					# 	relFinderPropertyQuery += """{?o3 <"""+ selectPropertyURLList[3] + """> ?o4.} UNION {?o4 <"""+ selectPropertyURLList[3] + """> ?o3.}\n"""
					if propertyDirectionList[3] == "ORIGIN":
						relFinderPropertyQuery += """?o3 <"""+ selectPropertyURLList[3] + """> ?o4.\n"""
					elif propertyDirectionList[3] == "DESTINATION":
						relFinderPropertyQuery += """?o4 <"""+ selectPropertyURLList[3] + """> ?o3.\n"""
				

							

			relFinderPropertyQuery += """
							VALUES ?place
							{"""
			for IRI in inplaceIRISubList:
				relFinderPropertyQuery = relFinderPropertyQuery + "<" + IRI + "> \n"

			relFinderPropertyQuery = relFinderPropertyQuery + """
							}
							}
							"""

			
			relFinderPropertySparqlParam = {'query': relFinderPropertyQuery, 'format': 'json'}
			relFinderPropertySparqlRequest = requests.get('https://query.wikidata.org/sparql', params=relFinderPropertySparqlParam)
			arcpy.AddMessage("SPARQL: {0}".format(relFinderPropertySparqlRequest.url))
			jsonBindingObject.extend(relFinderPropertySparqlRequest.json()["results"]["bindings"])

			i = i + 50

		tripleStore = dict()
		Triple = namedtuple("Triple", ["s", "p", "o"])
		for jsonItem in jsonBindingObject:
			if len(propertyDirectionList) > 0:
				# triple = []
				if selectPropertyURLList[0] == "":
					if propertyDirectionList[0] == "ORIGIN":
						# relFinderPropertyQuery += """?place ?p1 ?o1.\n"""
						currentTriple = Triple(s = jsonItem["place"]["value"], p = jsonItem["p1"]["value"], o = jsonItem["o1"]["value"])
					elif propertyDirectionList[0] == "DESTINATION":
						# relFinderPropertyQuery += """?o1 ?p1 ?place.\n"""
						currentTriple = Triple(s = jsonItem["o1"]["value"], p = jsonItem["p1"]["value"], o = jsonItem["place"]["value"])
						# triple = [jsonItem["o1"]["value"], jsonItem["p1"]["value"], jsonItem["place"]["value"]]
				else:
					if propertyDirectionList[0] == "ORIGIN":
						# relFinderPropertyQuery += """?place <"""+ selectPropertyURLList[0] + """> ?o1.\n"""
						currentTriple = Triple(s = jsonItem["place"]["value"], p = selectPropertyURLList[0], o = jsonItem["o1"]["value"])
						# triple = [jsonItem["place"]["value"], selectPropertyURLList[0], jsonItem["o1"]["value"]]
					elif propertyDirectionList[0] == "DESTINATION":
						# relFinderPropertyQuery += """?o1 <"""+ selectPropertyURLList[0] + """> ?place.\n"""
						currentTriple = Triple(s = jsonItem["o1"]["value"], p = selectPropertyURLList[0], o = jsonItem["place"]["value"])
						# triple = [jsonItem["o1"]["value"], selectPropertyURLList[0], jsonItem["place"]["value"]]

				if currentTriple not in tripleStore:
					tripleStore[currentTriple] = 1
				else:
					if tripleStore[currentTriple] > 1:
						tripleStore[currentTriple] = 1
				

			if len(propertyDirectionList) > 1:
				# triple = []
				if selectPropertyURLList[1] == "":
					if propertyDirectionList[1] == "ORIGIN":
						# relFinderPropertyQuery += """?o1 ?p2 ?o2.\n"""
						currentTriple = Triple(s = jsonItem["o1"]["value"], p = jsonItem["p2"]["value"], o = jsonItem["o2"]["value"])
						# triple = [jsonItem["o1"]["value"], jsonItem["p2"]["value"], jsonItem["o2"]["value"]]
					elif propertyDirectionList[1] == "DESTINATION":
						# relFinderPropertyQuery += """?o2 ?p2 ?o1.\n"""
						currentTriple = Triple(s = jsonItem["o2"]["value"], p = jsonItem["p2"]["value"], o = jsonItem["o1"]["value"])
						# triple = [jsonItem["o2"]["value"], jsonItem["p2"]["value"], jsonItem["o1"]["value"]]
				else:
					if propertyDirectionList[1] == "ORIGIN":
						# relFinderPropertyQuery += """?o1 <"""+ selectPropertyURLList[1] + """> ?o2.\n"""
						currentTriple = Triple(s = jsonItem["o1"]["value"], p = selectPropertyURLList[1], o = jsonItem["o2"]["value"])
						# triple = [jsonItem["o1"]["value"], selectPropertyURLList[1], jsonItem["o2"]["value"]]
					elif propertyDirectionList[1] == "DESTINATION":
						# relFinderPropertyQuery += """?o2 <"""+ selectPropertyURLList[1] + """> ?o1.\n"""
						currentTriple = Triple(s = jsonItem["o2"]["value"], p = selectPropertyURLList[1], o = jsonItem["o1"]["value"])
						# triple = [jsonItem["o2"]["value"], selectPropertyURLList[1], jsonItem["o1"]["value"]]

				if currentTriple not in tripleStore:
					tripleStore[currentTriple] = 2
				else:
					if tripleStore[currentTriple] > 2:
						tripleStore[currentTriple] = 2

			if len(propertyDirectionList) > 2:
				# triple = []
				if selectPropertyURLList[2] == "":
					if propertyDirectionList[2] == "ORIGIN":
						# relFinderPropertyQuery += """?o2 ?p3 ?o3.\n"""
						currentTriple = Triple(s = jsonItem["o2"]["value"], p = jsonItem["p3"]["value"], o = jsonItem["o3"]["value"])
						# triple = [jsonItem["o2"]["value"], jsonItem["p3"]["value"], jsonItem["o3"]["value"]]
					elif propertyDirectionList[2] == "DESTINATION":
						# relFinderPropertyQuery += """?o3 ?p3 ?o2.\n"""
						currentTriple = Triple(s = jsonItem["o3"]["value"], p = jsonItem["p3"]["value"], o = jsonItem["o2"]["value"])
						# triple = [jsonItem["o3"]["value"], jsonItem["p3"]["value"], jsonItem["o2"]["value"]]
				else:
					if propertyDirectionList[2] == "ORIGIN":
						# relFinderPropertyQuery += """?o2 <"""+ selectPropertyURLList[2] + """> ?o3.\n"""
						currentTriple = Triple(s = jsonItem["o2"]["value"], p = selectPropertyURLList[2], o = jsonItem["o3"]["value"])
						# triple = [jsonItem["o2"]["value"], selectPropertyURLList[2], jsonItem["o3"]["value"]]
					elif propertyDirectionList[2] == "DESTINATION":
						# relFinderPropertyQuery += """?o3 <"""+ selectPropertyURLList[2] + """> ?o2.\n"""
						currentTriple = Triple(s = jsonItem["o3"]["value"], p = selectPropertyURLList[2], o = jsonItem["o2"]["value"])
						# triple = [jsonItem["o3"]["value"], selectPropertyURLList[2], jsonItem["o2"]["value"]]

				if currentTriple not in tripleStore:
					tripleStore[currentTriple] = 3
				else:
					if tripleStore[currentTriple] > 3:
						tripleStore[currentTriple] = 3

			if len(propertyDirectionList) > 3:
				triple = []
				if selectPropertyURLList[3] == "":
					if propertyDirectionList[3] == "ORIGIN":
						# relFinderPropertyQuery += """?o3 ?p4 ?o4.\n"""
						currentTriple = Triple(s = jsonItem["o3"]["value"], p = jsonItem["p4"]["value"], o = jsonItem["o4"]["value"])
						# triple = [jsonItem["o3"]["value"], jsonItem["p4"]["value"], jsonItem["o4"]["value"]]
					elif propertyDirectionList[3] == "DESTINATION":
						# relFinderPropertyQuery += """?o4 ?p4 ?o3.\n"""
						currentTriple = Triple(s = jsonItem["o4"]["value"], p = jsonItem["p4"]["value"], o = jsonItem["o3"]["value"])
						# triple = [jsonItem["o4"]["value"], jsonItem["p4"]["value"], jsonItem["o3"]["value"]]
				else:
					if propertyDirectionList[3] == "ORIGIN":
						# relFinderPropertyQuery += """?o3 <"""+ selectPropertyURLList[3] + """> ?o4.\n"""
						currentTriple = Triple(s = jsonItem["o3"]["value"], p = selectPropertyURLList[3], o = jsonItem["o4"]["value"])
						# triple = [jsonItem["o3"]["value"], selectPropertyURLList[3], jsonItem["o4"]["value"]]
					elif propertyDirectionList[3] == "DESTINATION":
						# relFinderPropertyQuery += """?o4 <"""+ selectPropertyURLList[3] + """> ?o3.\n"""
						currentTriple = Triple(s = jsonItem["o4"]["value"], p = selectPropertyURLList[3], o = jsonItem["o3"]["value"])
						# triple = [jsonItem["o4"]["value"], selectPropertyURLList[3], jsonItem["o3"]["value"]]

				if currentTriple not in tripleStore:
					tripleStore[currentTriple] = 4
				
		# tripleStore = []
		# for jsonItem in jsonBindingObject:
		# 	if len(propertyDirectionList) > 0:
		# 		triple = []
		# 		if selectPropertyURLList[0] == "":
		# 			if propertyDirectionList[0] == "ORIGIN":
		# 				# relFinderPropertyQuery += """?place ?p1 ?o1.\n"""
		# 				triple = [jsonItem["place"]["value"], jsonItem["p1"]["value"], jsonItem["o1"]["value"]]
		# 			elif propertyDirectionList[0] == "DESTINATION":
		# 				# relFinderPropertyQuery += """?o1 ?p1 ?place.\n"""
		# 				triple = [jsonItem["o1"]["value"], jsonItem["p1"]["value"], jsonItem["place"]["value"]]
		# 		else:
		# 			if propertyDirectionList[0] == "ORIGIN":
		# 				# relFinderPropertyQuery += """?place <"""+ selectPropertyURLList[0] + """> ?o1.\n"""
		# 				triple = [jsonItem["place"]["value"], selectPropertyURLList[0], jsonItem["o1"]["value"]]
		# 			elif propertyDirectionList[0] == "DESTINATION":
		# 				# relFinderPropertyQuery += """?o1 <"""+ selectPropertyURLList[0] + """> ?place.\n"""
		# 				triple = [jsonItem["o1"]["value"], selectPropertyURLList[0], jsonItem["place"]["value"]]

		# 		if triple not in tripleStore:
		# 			tripleStore.append(triple)
				

		# 	if len(propertyDirectionList) > 1:
		# 		triple = []
		# 		if selectPropertyURLList[1] == "":
		# 			if propertyDirectionList[1] == "ORIGIN":
		# 				# relFinderPropertyQuery += """?o1 ?p2 ?o2.\n"""
		# 				triple = [jsonItem["o1"]["value"], jsonItem["p2"]["value"], jsonItem["o2"]["value"]]
		# 			elif propertyDirectionList[1] == "DESTINATION":
		# 				# relFinderPropertyQuery += """?o2 ?p2 ?o1.\n"""
		# 				triple = [jsonItem["o2"]["value"], jsonItem["p2"]["value"], jsonItem["o1"]["value"]]
		# 		else:
		# 			if propertyDirectionList[1] == "ORIGIN":
		# 				# relFinderPropertyQuery += """?o1 <"""+ selectPropertyURLList[1] + """> ?o2.\n"""
		# 				triple = [jsonItem["o1"]["value"], selectPropertyURLList[1], jsonItem["o2"]["value"]]
		# 			elif propertyDirectionList[1] == "DESTINATION":
		# 				# relFinderPropertyQuery += """?o2 <"""+ selectPropertyURLList[1] + """> ?o1.\n"""
		# 				triple = [jsonItem["o2"]["value"], selectPropertyURLList[1], jsonItem["o1"]["value"]]

		# 		if triple not in tripleStore:
		# 			tripleStore.append(triple)

		# 	if len(propertyDirectionList) > 2:
		# 		triple = []
		# 		if selectPropertyURLList[2] == "":
		# 			if propertyDirectionList[2] == "ORIGIN":
		# 				# relFinderPropertyQuery += """?o2 ?p3 ?o3.\n"""
		# 				triple = [jsonItem["o2"]["value"], jsonItem["p3"]["value"], jsonItem["o3"]["value"]]
		# 			elif propertyDirectionList[2] == "DESTINATION":
		# 				# relFinderPropertyQuery += """?o3 ?p3 ?o2.\n"""
		# 				triple = [jsonItem["o3"]["value"], jsonItem["p3"]["value"], jsonItem["o2"]["value"]]
		# 		else:
		# 			if propertyDirectionList[2] == "ORIGIN":
		# 				# relFinderPropertyQuery += """?o2 <"""+ selectPropertyURLList[2] + """> ?o3.\n"""
		# 				triple = [jsonItem["o2"]["value"], selectPropertyURLList[2], jsonItem["o3"]["value"]]
		# 			elif propertyDirectionList[2] == "DESTINATION":
		# 				# relFinderPropertyQuery += """?o3 <"""+ selectPropertyURLList[2] + """> ?o2.\n"""
		# 				triple = [jsonItem["o3"]["value"], selectPropertyURLList[2], jsonItem["o2"]["value"]]

		# 		if triple not in tripleStore:
		# 			tripleStore.append(triple)

		# 	if len(propertyDirectionList) > 3:
		# 		triple = []
		# 		if selectPropertyURLList[3] == "":
		# 			if propertyDirectionList[3] == "ORIGIN":
		# 				# relFinderPropertyQuery += """?o3 ?p4 ?o4.\n"""
		# 				triple = [jsonItem["o3"]["value"], jsonItem["p4"]["value"], jsonItem["o4"]["value"]]
		# 			elif propertyDirectionList[3] == "DESTINATION":
		# 				# relFinderPropertyQuery += """?o4 ?p4 ?o3.\n"""
		# 				triple = [jsonItem["o4"]["value"], jsonItem["p4"]["value"], jsonItem["o3"]["value"]]
		# 		else:
		# 			if propertyDirectionList[3] == "ORIGIN":
		# 				# relFinderPropertyQuery += """?o3 <"""+ selectPropertyURLList[3] + """> ?o4.\n"""
		# 				triple = [jsonItem["o3"]["value"], selectPropertyURLList[3], jsonItem["o4"]["value"]]
		# 			elif propertyDirectionList[3] == "DESTINATION":
		# 				# relFinderPropertyQuery += """?o4 <"""+ selectPropertyURLList[3] + """> ?o3.\n"""
		# 				triple = [jsonItem["o4"]["value"], selectPropertyURLList[3], jsonItem["o3"]["value"]]

		# 		if triple not in tripleStore:
		# 			tripleStore.append(triple)


		return tripleStore











class UTIL(object):
	# @staticmethod
	# def addTriple2TripleStore(tripleStore, newTriple):
	# 	# newTriple: [subject, predicate, object, degree]
	# 	# add newTriple to the tripleStore. 
	# 	# If S-P-O is in the tripleStore, update the degree to the smaller one between the original degree in tripleSpre and the one in newTriple
	# 	# If S-P-O is not in the tripleStore, add it
	# 	isInTripleStore = False
	# 	for element in tripleStore:
	# 		if element[0] == newTriple[0] and element[1] == newTriple[1] and element[2] == newTriple[2]:
	@staticmethod
	def mergeTripleStoreDicts(superTripleStore, childTripleStore):
		# superTripleStore and childTripleStore: dict() object with key nameTuple Triple("Triple",["s", "p", "o"])
		# add childTripleStore to superTripleStore. 
		# If S-P-O is in the superTripleStore, update the degree to the smaller one between the original degree in superTripleStore and the one in childTripleStore
		# If S-P-O is not in the superTripleStore, add it
		for triple in childTripleStore:
			if triple not in superTripleStore:
				superTripleStore[triple] = childTripleStore[triple]
			else:
				if superTripleStore[triple] > childTripleStore[triple]:
					superTripleStore[triple] = childTripleStore[triple]

		return superTripleStore


	@staticmethod
	def mergeListsWithUniqueElement(superList, childList):
		# merge childList to superList, append the elements which are not in superList to superList
		for element in childList:
			if element not in superList:
				superList.append(element)

		return superList

	@staticmethod
	def directionListFromBoth2OD(propertyDirectionList):
		# given a list of direction, return a list of lists which change a list with "BOTH" to two list with "ORIGIN" and "DESTINATION"
		# e.g. ["BOTH", "ORIGIN", "DESTINATION", "ORIGIN"] -> ["ORIGIN", "ORIGIN", "DESTINATION", "ORIGIN"] and ["DESTINATION", "ORIGIN", "DESTINATION", "ORIGIN"]
		# propertyDirectionList: a list of direction from ["BOTH", "ORIGIN", "DESTINATION"], it has at most 4 elements

		propertyDirectionExpandedLists = []
		propertyDirectionExpandedLists.append(propertyDirectionList)

		resultList = []

		for currentPropertyDirectionList in propertyDirectionExpandedLists:
			i = 0
			indexOfBOTH = -1
			while i < len(currentPropertyDirectionList):
				if currentPropertyDirectionList[i] == "BOTH":
					indexOfBOTH = i
					break
				i = i + 1

			if indexOfBOTH != -1:
				newList1 = currentPropertyDirectionList[:]
				newList1[indexOfBOTH] = "ORIGIN"
				propertyDirectionExpandedLists.append(newList1)

				newList2 = currentPropertyDirectionList[:]
				newList2[indexOfBOTH] = "DESTINATION"
				propertyDirectionExpandedLists.append(newList2)

			else:
				if currentPropertyDirectionList not in resultList:
					resultList.append(currentPropertyDirectionList)

		return resultList

				
		
	
	@staticmethod
	def buildMultiValueDictFromNoFunctionalProperty(fieldName, tableName):
		# build a collections.defaultdict object to store the multivalue for each no-functional property's subject. 
		# The subject "wikiURL" is the key, the corespnding property value in "fieldName" is the value
		if UTIL.isFieldNameInTable(fieldName, tableName):
			noFunctionalPropertyDict = defaultdict(list)
			# fieldList = arcpy.ListFields(tableName)

			srows = None
			srows = arcpy.SearchCursor(tableName, '', '', '', '{0} A;{1} A'.format('wikiURL', fieldName))
			for row in srows:
				foreignKeyValue = row.getValue('wikiURL')
				noFunctionalPropertyValue = row.getValue(fieldName)
				# if from_field in ['Double', 'Float']:
				#     value = locale.format('%s', (row.getValue(from_field)))
				if noFunctionalPropertyValue <> None:
					noFunctionalPropertyDict[foreignKeyValue].append(noFunctionalPropertyValue)

			return noFunctionalPropertyDict
		else:
			return -1


	@staticmethod
	def appendFieldInFeatureClassByMergeRule(inputFeatureClassName, noFunctionalPropertyDict, appendFieldName, relatedTableName, mergeRule, delimiter):
		# append a new field in inputFeatureClassName which will install the merged no-functional property value
		# noFunctionalPropertyDict: the collections.defaultdict object which stores the no-functional property value for each URL
		# appendFieldName: the field name of no-functional property in the relatedTableName
		# mergeRule: the merge rule the user selected, one of ['SUM', 'MIN', 'MAX', 'STDEV', 'MEAN', 'COUNT', 'FIRST', 'LAST']
		# delimiter: the optional paramter which define the delimiter of the cancatenate operation
		appendFieldType = ''
		appendFieldLength = 0
		fieldList = arcpy.ListFields(relatedTableName)
		for field in fieldList:
			if field.name == appendFieldName:
				appendFieldType = field.type
				if field.type == "String":
					appendFieldLength = field.length
				break
		mergeRuleField = ''
		if mergeRule == 'SUM':
			mergeRuleField = 'SUM'
		elif mergeRule == 'MIN':
			mergeRuleField = 'MIN'
		elif mergeRule == 'MAX':
			mergeRuleField = 'MAX'
		elif mergeRule == 'STDEV':
			mergeRuleField = 'STD'
		elif mergeRule == 'MEAN':
			mergeRuleField = 'MEN'
		elif mergeRule == 'COUNT':
			mergeRuleField = 'COUNT'
		elif mergeRule == 'FIRST':
			mergeRuleField = 'FIRST'
		elif mergeRule == 'LAST':
			mergeRuleField = 'LAST'
		elif mergeRule == 'CONCATENATE':
			mergeRuleField = 'CONCAT'

		if appendFieldType != "String":
			cursor = arcpy.SearchCursor(relatedTableName)
			for row in cursor:
				rowValue = row.getValue(appendFieldName)
				if appendFieldLength < len(str(rowValue)):
					appendFieldLength = len(str(rowValue))
		# subFieldName = appendFieldName[:5]
		# arcpy.AddMessage("subFieldName: {0}".format(subFieldName))

		# featureClassAppendFieldName = subFieldName + "_" + mergeRuleField
		featureClassAppendFieldName = appendFieldName + "_" + mergeRuleField
		newAppendFieldName = UTIL.getFieldNameWithTable(featureClassAppendFieldName, inputFeatureClassName)
		if newAppendFieldName != -1:
			if mergeRule == 'COUNT':
				arcpy.AddField_management(inputFeatureClassName, newAppendFieldName, "SHORT")
			elif mergeRule == 'STDEV' or mergeRule == 'MEAN':
				arcpy.AddField_management(inputFeatureClassName, newAppendFieldName, "DOUBLE")
			elif mergeRule == 'CONCATENATE':
				# get the maximum number of values for current property: maxNumOfValue
				# maxNumOfValue * field.length = the length of new append field
				maxNumOfValue = 1
				for key in noFunctionalPropertyDict:
					if maxNumOfValue < len(noFunctionalPropertyDict[key]):
						maxNumOfValue = len(noFunctionalPropertyDict[key])
				
				arcpy.AddField_management(inputFeatureClassName, newAppendFieldName, 'TEXT', field_length=appendFieldLength * maxNumOfValue)
				
				
			else:
				if appendFieldType == "String":
					arcpy.AddField_management(inputFeatureClassName, newAppendFieldName, appendFieldType, field_length=appendFieldLength)
				else:
					arcpy.AddField_management(inputFeatureClassName, newAppendFieldName, appendFieldType)

			if UTIL.isFieldNameInTable("URL", inputFeatureClassName):
				urows = None
				urows = arcpy.UpdateCursor(inputFeatureClassName)
				for row in urows:
					foreignKeyValue = row.getValue("URL")
					noFunctionalPropertyValueList = noFunctionalPropertyDict[foreignKeyValue]
					if len(noFunctionalPropertyValueList) != 0:
						rowValue = ""
						# if mergeRule in ['STDEV', 'MEAN']:
						# 	if appendFieldType in ['Single', 'Double']:
						# 		if mergeRule == 'MEAN':
						# 			rowValue = numpy.average(noFunctionalPropertyValueList)
						# 		elif mergeRule == 'STDEV':
						# 			rowValue = numpy.std(noFunctionalPropertyValueList)
						# 	else:
						# 		arcpy.AddError("The {0} data type of Field {1} does not support {2} merge rule".format(appendFieldType, appendFieldName, mergeRule))
						# 		raise arcpy.ExecuteError
						# elif mergeRule in ['SUM', 'MIN', 'MAX']:
						# 	if appendFieldType in ['Single', 'Double', 'SmallInteger', 'Integer']:
						# 		if mergeRule == 'SUM':
						# 			rowValue = numpy.sum(noFunctionalPropertyValueList)
						# 		elif mergeRule == 'MIN':
						# 			rowValue = numpy.amin(noFunctionalPropertyValueList)
						# 		elif mergeRule == 'MAX':
						# 			rowValue = numpy.amax(noFunctionalPropertyValueList)
						# 	else:
						# 		arcpy.AddError("The {0} data type of Field {1} does not support {2} merge rule".format(appendFieldType, appendFieldName, mergeRule))
						if mergeRule in ['STDEV', 'MEAN', 'SUM', 'MIN', 'MAX']:
							if appendFieldType in ['Single', 'Double', 'SmallInteger', 'Integer']:
								if mergeRule == 'MEAN':
									rowValue = numpy.average(noFunctionalPropertyValueList)
								elif mergeRule == 'STDEV':
									rowValue = numpy.std(noFunctionalPropertyValueList)
								elif mergeRule == 'SUM':
									rowValue = numpy.sum(noFunctionalPropertyValueList)
								elif mergeRule == 'MIN':
									rowValue = numpy.amin(noFunctionalPropertyValueList)
								elif mergeRule == 'MAX':
									rowValue = numpy.amax(noFunctionalPropertyValueList)
							else:
								arcpy.AddError("The {0} data type of Field {1} does not support {2} merge rule".format(appendFieldType, appendFieldName, mergeRule))
						elif mergeRule in ['COUNT', 'FIRST', 'LAST']:
							if mergeRule == 'COUNT':
								rowValue = len(noFunctionalPropertyValueList)
							elif mergeRule == 'FIRST':
								rowValue = noFunctionalPropertyValueList[0]
							elif mergeRule == 'LAST':
								rowValue = noFunctionalPropertyValueList[len(noFunctionalPropertyValueList)-1]
						elif mergeRule == 'CONCATENATE':
							value = ""
							if appendFieldType in ['String']:
								rowValue = delimiter.join(sorted(set([val for val in noFunctionalPropertyValueList if not value is None])))
							else:
								rowValue = delimiter.join(sorted(set([str(val) for val in noFunctionalPropertyValueList if not value is None])))

						row.setValue(newAppendFieldName, rowValue)
						urows.updateRow(row)






	@staticmethod
	def getPropertyName(propertyURL):
		# give a URL of property, get the property name (without prefix)
		if "#" in propertyURL:
			lastIndex = propertyURL.rfind("#")
			propertyName = propertyURL[(lastIndex+1):]
		else:
			lastIndex = propertyURL.rfind("/")
			propertyName = propertyURL[(lastIndex+1):]

		return propertyName

	@staticmethod
	def getFieldNameWithTable(propertyName, inputFeatureClassName):
		# give a property Name which have been sliced by getPropertyName(propertyURL)
		# decide whether its lengh is larger than 10
		# decide whether it is already in the feature class table
		# return the final name of this field, if return -1, that mean the field name has more than 10 times in this table, you just do nothing
		# if len(propertyName) > 10:
		# 	propertyName = propertyName[:9]
		
		isfieldNameinTable = UTIL.isFieldNameInTable(propertyName, inputFeatureClassName)
		if isfieldNameinTable == False:
			return propertyName
		else:
			return UTIL.changeFieldNameWithTable(propertyName, inputFeatureClassName)


	@staticmethod
	def changeFieldNameWithTable(propertyName, inputFeatureClassName):
		for i in range(1,10):
			propertyName = propertyName[:(len(propertyName)-1)] + str(i)
			isfieldNameinTable = UTIL.isFieldNameInTable(propertyName, inputFeatureClassName)
			if isfieldNameinTable == False:
				return propertyName

		return -1

		

	@staticmethod
	def isFieldNameInTable(fieldName, inputFeatureClassName):
		fieldList = arcpy.ListFields(inputFeatureClassName)
		isfieldNameinFieldList = False
		for field in fieldList:
			if field.name == fieldName:
				isfieldNameinFieldList = True
				break

		return isfieldNameinFieldList

	@staticmethod
	def getFieldLength(fieldName, inputFeatureClassName):
		fieldList = arcpy.ListFields(inputFeatureClassName)
		for field in fieldList:
			if field.name == fieldName:
				return field.length

		return -1

	@staticmethod
	def getFieldDataTypeInTable(fieldName, inputFeatureClassName):
		fieldList = arcpy.ListFields(inputFeatureClassName)
		for field in fieldList:
			if field.name == fieldName:
				return field.type

		return -1

	@staticmethod
	def detectRelationship(inputFeatureClassName, inputTableName):
		# given full path of feature class and table, decide whether there are a relationship class in this current fiel geodatabase between them
		# return False, if inputFeatureClassName and inputTableName are in different filegeodatabase
		lastIndexOFGDB = inputFeatureClassName.rfind("\\")
		featureClassName = inputFeatureClassName[(lastIndexOFGDB+1):]
		featureClassWorkspace = inputFeatureClassName[:lastIndexOFGDB]

		lastIndexOFTable = inputTableName.rfind("\\")
		tableName = inputTableName[(lastIndexOFTable+1):]
		tableWorkspace = inputTableName[:lastIndexOFTable]

		isFeatureClassAndTableRelated = False

		# arcpy.AddMessage("featureClassName: {0}".format(featureClassName))
		# arcpy.AddMessage("tableName: {0}".format(tableName))
		
		if featureClassWorkspace == tableWorkspace and featureClassWorkspace.endswith(".gdb"):
			workspace = featureClassWorkspace
			rc_list = [c.name for c in arcpy.Describe(workspace).children if c.datatype == "RelationshipClass"]  
			for rc in rc_list: 
				rc_path = workspace + "\\" + rc  
				des_rc = arcpy.Describe(rc_path)  
				origin = des_rc.originClassNames  
				destination = des_rc.destinationClassNames  
				# print "Relationship Class: %s \n Origin: %s \n Desintation: %s" %(rc, origin, destination)
				# arcpy.AddMessage("Relationship Class: {0} \n Origin: {1} \n Desintation: {2}".format(rc, origin, destination))
				if origin[0] == featureClassName and destination[0] == tableName:
					isFeatureClassAndTableRelated = True
					# arcpy.AddMessage("Yes!!!!!!!!!!!")
					break

		return isFeatureClassAndTableRelated

	@staticmethod
	def getRelatedTableFromFeatureClass(inputFeatureClassName):
		# given full path of feature class, get a list of table which are related to it
		# return a list of table names who are related to the input feature class in the current file geodatabase
		lastIndexOFGDB = inputFeatureClassName.rfind("\\")
		featureClassName = inputFeatureClassName[(lastIndexOFGDB+1):]
		workspace = inputFeatureClassName[:lastIndexOFGDB]


		# arcpy.AddMessage("featureClassName: {0}".format(featureClassName))
		# arcpy.AddMessage("tableName: {0}".format(tableName))
		relatedTableList = []
		if workspace.endswith(".gdb"):
			for c in arcpy.Describe(workspace).children:
				# arcpy.AddMessage("c: ".format(c))
				if c.datatype == "RelationshipClass":
					rc_path = workspace + "\\" + c.name
					# arcpy.AddMessage("rc_path: {0}".format(rc_path))
					des_rc = arcpy.Describe(rc_path)
					origin = des_rc.originClassNames
					# arcpy.AddMessage("origin: {0}".format(origin[0]))
					if origin[0] == featureClassName:
						destination = des_rc.destinationClassNames
						relatedTableList.append(workspace + "\\" + destination[0])

		arcpy.AddMessage("relatedTableList: {0}".format(relatedTableList))

		return relatedTableList

	@staticmethod
	def getRelationshipClassFromFeatureClass(inputFeatureClassName):
		# given full path of feature class, get a list of relationship class which are related to it
		# return a list of relationship class name whose origin is the input feature class in the current file geodatabase
		lastIndexOFGDB = inputFeatureClassName.rfind("\\")
		featureClassName = inputFeatureClassName[(lastIndexOFGDB+1):]
		workspace = inputFeatureClassName[:lastIndexOFGDB]


		# arcpy.AddMessage("featureClassName: {0}".format(featureClassName))
		# arcpy.AddMessage("tableName: {0}".format(tableName))
		relatedRelationshipClassList = []
		if workspace.endswith(".gdb"):
			for c in arcpy.Describe(workspace).children:
				# arcpy.AddMessage("c: ".format(c))
				if c.datatype == "RelationshipClass":
					rc_path = workspace + "\\" + c.name
					# arcpy.AddMessage("rc_path: {0}".format(rc_path))
					des_rc = arcpy.Describe(rc_path)
					origin = des_rc.originClassNames
					# arcpy.AddMessage("origin: {0}".format(origin[0]))
					if origin[0] == featureClassName:
						destination = des_rc.destinationClassNames
						relatedRelationshipClassList.append(rc_path)

		arcpy.AddMessage("relatedRelationshipClassList from Feature Class: {0}".format(relatedRelationshipClassList))

		return relatedRelationshipClassList


	@staticmethod
	def getRelationshipClassFromTable(inputTableName):
		# given full path of table, get a list of relationship class which are related to it
		# return a list of relationship class name whose destination is the table in the current file geodatabase
		lastIndexOFGDB = inputTableName.rfind("\\")
		tableName = inputTableName[(lastIndexOFGDB+1):]
		workspace = inputTableName[:lastIndexOFGDB]


		# arcpy.AddMessage("featureClassName: {0}".format(featureClassName))
		# arcpy.AddMessage("tableName: {0}".format(tableName))
		relatedRelationshipClassList = []
		if workspace.endswith(".gdb"):
			for c in arcpy.Describe(workspace).children:
				# arcpy.AddMessage("c: ".format(c))
				if c.datatype == "RelationshipClass":
					rc_path = workspace + "\\" + c.name
					# arcpy.AddMessage("rc_path: {0}".format(rc_path))
					des_rc = arcpy.Describe(rc_path)
					destination = des_rc.destinationClassNames
					# arcpy.AddMessage("origin: {0}".format(origin[0]))
					if destination[0] == tableName:
						origin = des_rc.originClassNames
						relatedRelationshipClassList.append(rc_path)

		arcpy.AddMessage("relatedRelationshipClassList from Feature Class: {0}".format(relatedRelationshipClassList))

		return relatedRelationshipClassList
	



















class Json2Field(object):
	@staticmethod
	def creatPlaceFeatureClassFromJSON(jsonBindingObject, endFeatureClassName, selectedURL, inPlaceType):
		# After querying the information of location entities, we get the information and create a feature class from them
		arcpy.AddMessage("jsonBindingObject: {0}".format(jsonBindingObject))
		# a set of unique Coordinates for each found places
		placeIRISet = Set()
		placeList = []
		for item in jsonBindingObject:
			print "%s\t%s\t%s" % (
				item["place"]["value"], item["placeLabel"]["value"],
				item["location"]["value"])
			# arcpy.AddMessage("endFeatureClass: {0}\t{1}\t{2}".format(item["place"]["value"], item["placeLabel"]["value"],item["location"]["value"]))
			if len(placeIRISet) == 0 or item["place"]["value"] not in placeIRISet:
				placeIRISet.add(item["place"]["value"])
				coordItem = item["location"]["value"]
				coordList = re.split("[( )]", coordItem)
				itemlat = coordList[2]
				itemlng = coordList[1]
				placeList.append([item["place"]["value"], item["placeLabel"]["value"], itemlat, itemlng])

		if len(placeList) == 0:
			arcpy.AddMessage("No location information can be finded!")
		else:

			# Spatial reference set to GCS_WGS_1984
			spatial_reference = arcpy.SpatialReference(4326)
			# creat a Point feature class in arcpy
			pt = arcpy.Point()
			ptGeoms = []
			for p in placeList:
				pt.X = float(p[3])
				pt.Y = float(p[2])
				pointGeometry = arcpy.PointGeometry(pt, spatial_reference)
				ptGeoms.append(pointGeometry)

			arcpy.AddMessage("ptGeoms: {0}".format(ptGeoms))
			arcpy.AddMessage("endFeatureClassName: {0}".format(endFeatureClassName))

			if endFeatureClassName == None:
				arcpy.AddMessage("No data will be added to the map document.")
			else:
				# create a geometry Feature class to represent 
				endFeatureClass = arcpy.CopyFeatures_management(ptGeoms, endFeatureClassName)

				# add field to this point feature class
				arcpy.AddField_management(endFeatureClass, "Label", "TEXT", field_length=50)
				arcpy.AddField_management(endFeatureClass, "URL", "TEXT", field_length=50)
				# arcpy.AddField_management(placeNearFeatureClass, "TypeURL", "TEXT", field_length=50)
				# arcpy.AddField_management(placeNearFeatureClass, "TypeName", "TEXT", field_length=50)
				if selectedURL != None:
					arcpy.AddField_management(placeNearFeatureClass, "BTypeURL", "TEXT", field_length=50)
					arcpy.AddField_management(placeNearFeatureClass, "BTypeName", "TEXT", field_length=50)
				# arcpy.AddField_management(placeNearFeatureClass, "Latitude", "TEXT", 10, 10)
				# arcpy.AddField_management(placeNearFeatureClass, "Longitude", "TEXT", 10, 10)

				arcpy.AddXY_management(endFeatureClass)
				# add label, latitude, longitude value to this point feature class

				i = 0
				cursor = arcpy.UpdateCursor(endFeatureClassName)
				row = cursor.next()
				while row:
					row.setValue("Label", placeList[i][1])
					row.setValue("URL", placeList[i][0])
					# row.setValue("TypeURL", placeList[i][5])
					# row.setValue("TypeName", placeList[i][6])
					cursor.updateRow(row)
					i = i + 1
					row = cursor.next()

				if selectedURL != None:
					i = 0
					cursor = arcpy.UpdateCursor(endFeatureClassName)
					row = cursor.next()
					while row:
						row.setValue("BTypeURL", selectedURL)
						row.setValue("BTypeName", inPlaceType)
						cursor.updateRow(row)
						i = i + 1
						row = cursor.next()




				mxd = arcpy.mapping.MapDocument("CURRENT")

				# get the data frame
				df = arcpy.mapping.ListDataFrames(mxd)[0]

				# create a new layer
				endFeatureClassLayer = arcpy.mapping.Layer(endFeatureClassName)

				# add the layer to the map at the bottom of the TOC in data frame 0
				arcpy.mapping.AddLayer(df, endFeatureClassLayer, "BOTTOM")


	@staticmethod
	def createLocationLinkageMappingTableFromJSON(jsonBindingObject, originField, endField, originFeatureClassName, endFeatureClassName, locationCommonPropertyURL, locationCommonPropertyName, relationDegree):
		# After a sparql query to find the linked location entities by a specific location commom property, we create a sperate table to install the linkage information from the originFeatureClassName to endFeatureClassName
		# jsonBindingObject: the SPARQl query JSOn result contains the linkage information
		# originField: the Field name and the variable name which represent the original location features
		# originFeatureClassName: the full path of the original feature class
		# endFeatureClassName: the full path of the end feature class
		# endField: the Field name and the variable name which represent the end location features
		# locationCommonPropertyURL: a specific location commom property which linked the originFeatureClassName to endFeatureClassName
		# locationCommonPropertyName: the lable of this location commom property, like the label of wd:P17 -> wdt:P17
		# relationDegree: the degree of relation between origin and end locations

		lastIndexOFGDB = originFeatureClassName.rfind("\\")
		originLocation = originFeatureClassName[:lastIndexOFGDB]
		originName = originFeatureClassName[(lastIndexOFGDB+1):]

		lastIndexOFGDB = endFeatureClassName.rfind("\\")
		endLocation = endFeatureClassName[:lastIndexOFGDB]
		endName = endFeatureClassName[(lastIndexOFGDB+1):]


		# currentValuePropertyName = UTIL.getPropertyName(valuePropertyURL)
		if originLocation.endswith(".gdb") == False or originLocation != endLocation:
			return -1
		else:
			outputLocation = originLocation
			PropertyName = locationCommonPropertyName.replace(" ", "_")
			tableName = originName + "_" + endName + "_" + "D"+ str(relationDegree) + "_" + PropertyName
			

			tablePath = Json2Field.getNoExistTableNameInWorkspace(outputLocation, tableName)

			lastIndexOftableName = tablePath.rfind("\\")
			tableName = tablePath[(lastIndexOftableName+1):]
			arcpy.AddMessage("outputLocation: {0}".format(outputLocation))
			arcpy.AddMessage("tableName: {0}".format(tableName))
			# create a table in current workspace
			locationLinkageTable = arcpy.CreateTable_management(outputLocation, tableName)
			arcpy.AddField_management(locationLinkageTable, originField, "TEXT", field_length=50)
			arcpy.AddField_management(locationLinkageTable, endField, "TEXT", field_length=50)

			arcpy.AddField_management(locationLinkageTable, "propURL", "TEXT", field_length=len(locationCommonPropertyURL))
			arcpy.AddField_management(locationLinkageTable, "propName", "TEXT", field_length=len(locationCommonPropertyName))
			arcpy.AddField_management(locationLinkageTable, "reDegree", "LONG")

			# Create insert cursor for table
			rows = arcpy.InsertCursor(locationLinkageTable)

			
			for jsonItem in jsonBindingObject:
				row = rows.newRow()
				row.setValue(originField, jsonItem[originField]["value"])
				row.setValue(endField, jsonItem[endField]["value"])
				row.setValue("propURL", locationCommonPropertyURL)
				row.setValue("propName", locationCommonPropertyName)
				row.setValue("reDegree", relationDegree)
				rows.insertRow(row)

			# Delete cursor and row objects to remove locks on the data
			# del row
			# del rows

			return tableName

	@staticmethod
	def getNoExistTableNameInWorkspace(outputLocation, tableName):
		# given a table name and a worksapce, we what to see whether this table alreay exists in this workspace, if it does, change the table name until it does not exist
		tablePath = outputLocation + "\\" + tableName
		if tablePath.endswith(".dbf"):
			if arcpy.Exists(tablePath):
				i = 1
				lastIndex = tablePath.rfind(".")
				tablePath = tablePath[:lastIndex]
				tablePath += "_" + str(i) + ".dbf"
				while arcpy.Exists(tablePath):
					i = i + 1
					lastIndex = tablePath.rfind("_")
					tablePath = tablePath[:lastIndex]
					tablePath += "_" + str(i) + ".dbf"

		else:
			if arcpy.Exists(tablePath):
				i = 1
				tablePath += "_" + str(i)
				while arcpy.Exists(tablePath):
					i = i + 1
					lastIndex = tablePath.rfind("_")
					tablePath = tablePath[:lastIndex]
					tablePath += "_" + str(i)


		return tablePath

	@staticmethod
	def createMappingTableFromJSON(jsonBindingObject, keyPropertyName, valuePropertyName, valuePropertyURL, inputFeatureClassName, keyPropertyFieldName, isInverse, isSubDivisionTable):
		# according to jsonBindingObject, create a sperate table to store the nofunctional property-value pairs 
		# OR store the transtive "isPartOf" relationship between location and its subDivision
		# return the name of the table without the full path
		# isInverse: Boolean variable indicates whether the value we get is the subject value or object value of valuePropertyURL
		# isSubDivisionTable: Boolean variable indicates whether the current table store the value of subdivision for the original location
		lastIndexOFGDB = inputFeatureClassName.rfind("\\")
		outputLocation = inputFeatureClassName[:lastIndexOFGDB]

		lastIndexOFFeatureClassName = inputFeatureClassName.rfind("\\")
		featureClassName = inputFeatureClassName[(lastIndexOFGDB+1):]

		currentValuePropertyName = UTIL.getPropertyName(valuePropertyURL)
		if isInverse == True:
			currentValuePropertyName = "is_" + currentValuePropertyName + "_Of"
		if isSubDivisionTable == True:
			currentValuePropertyName = "subDivisionIRI"
		if outputLocation.endswith(".gdb"):
			tableName = featureClassName + "_" + keyPropertyFieldName + "_" + currentValuePropertyName
			# propertyTable = arcpy.CreateTable_management(outputLocation, "wikiURL_"+currentValuePropertyName)
		else:
			lastIndexOFshp = featureClassName.rfind(".")
			featureClassName = featureClassName[:lastIndexOFshp]
			tableName =  featureClassName + "_" + keyPropertyFieldName + "_" + currentValuePropertyName+".dbf"
			# propertyTable = arcpy.CreateTable_management(outputLocation, "wikiURL_"+currentValuePropertyName+".dbf")

		tablePath = Json2Field.getNoExistTableNameInWorkspace(outputLocation, tableName)

		lastIndexOftableName = tablePath.rfind("\\")
		tableName = tablePath[(lastIndexOftableName+1):]
		# create a table in current workspace
		propertyTable = arcpy.CreateTable_management(outputLocation, tableName)
		keyPropertyFieldLength = Json2Field.fieldLengthDecide(jsonBindingObject, keyPropertyName)
		arcpy.AddField_management(propertyTable, keyPropertyFieldName, "TEXT", field_length=keyPropertyFieldLength)
		
		# if len(currentValuePropertyName) > 10:
		# 	currentValuePropertyName = currentValuePropertyName[:9]

		valuePropertyFieldType = Json2Field.fieldDataTypeDecide(jsonBindingObject, valuePropertyName)
		arcpy.AddMessage("valuePropertyURL: {0}".format(valuePropertyURL))
		arcpy.AddMessage("valuePropertyFieldType: {0}".format(valuePropertyFieldType))
		if valuePropertyFieldType == "TEXT":
			valuePropertyFieldLength = Json2Field.fieldLengthDecide(jsonBindingObject, valuePropertyName)
			arcpy.AddMessage("valuePropertyFieldLength: {0}".format(valuePropertyFieldLength))
			arcpy.AddField_management(propertyTable, currentValuePropertyName, valuePropertyFieldType, field_length=valuePropertyFieldLength)
		else:
			arcpy.AddField_management(propertyTable, currentValuePropertyName, valuePropertyFieldType)

		# arcpy.AddField_management(propertyTable, "propURL", "TEXT", field_length=len(valuePropertyURL))

		PropertyValue = namedtuple("PropertyValue", ["key", "value"])
		propertyValueSet = Set()
		for jsonItem in jsonBindingObject:
			pair = PropertyValue(key=jsonItem[keyPropertyName]["value"], value=jsonItem[valuePropertyName]["value"])
			propertyValueSet.add(pair)

		propertyValueList = list(propertyValueSet)


		# Create insert cursor for table
		rows = arcpy.InsertCursor(propertyTable)

		for pair in propertyValueList:
			row = rows.newRow()
			row.setValue(keyPropertyFieldName, pair.key)
			row.setValue(currentValuePropertyName, pair.value)
			# row.setValue("propURL", valuePropertyURL)
			rows.insertRow(row)
		
		# for jsonItem in jsonBindingObject:
		# 	row = rows.newRow()
		# 	row.setValue("wikiURL", jsonItem[keyPropertyName]["value"])
		# 	row.setValue(currentValuePropertyName, jsonItem[valuePropertyName]["value"])
		# 	# row.setValue("propURL", valuePropertyURL)
		# 	rows.insertRow(row)

		# Delete cursor and row objects to remove locks on the data
		del row
		del rows

		return tableName

	@staticmethod
	def buildDictFromJSONToModifyTable(jsonBindingObject, keyPropertyName, valuePropertyName):
		valuePropertyList = []
		keyPropertyList = []
		for jsonItem in jsonBindingObject:
			valuePropertyList.append(jsonItem[valuePropertyName]["value"])
			keyPropertyList.append(jsonItem[keyPropertyName]["value"])

		keyValueDict = dict(zip(keyPropertyList, valuePropertyList))
		arcpy.AddMessage("keyValueDict: {0}".format(keyValueDict))
		return keyValueDict

	@staticmethod
	def buildDictFromJSONToModifyMultiKeyTable(jsonBindingObject, keyPropertyNameList, valuePropertyName):
		# create a dict() object. Use multiple value as keys
		# jsonBindingObject: the json object from sparql query which contains the mapping from keyProperty to valueProperty, ex. functionalPropertyJSON
		# keyPropertyNameList: a list of the names of keyProperty in JSON object, ex. wikidataSub, s
		# valuePropertyName: the name of valueProperty in JSON object, ex. o
		MultiKey = namedtuple("MultiKey", keyPropertyNameList)

		keyValueDict = dict()
		for jsonItem in jsonBindingObject:
			MultiKeyValueList = []
			i = 0
			while i < len(keyPropertyNameList):
				MultiKeyValueList.append(jsonItem[keyPropertyNameList[i]]["value"])
				i = i + 1
			currentMultiKey = MultiKey._make(MultiKeyValueList)
			keyValueDict[currentMultiKey] = jsonItem[valuePropertyName]["value"]

		arcpy.AddMessage("keyValueDict: {0}".format(keyValueDict))
		return keyValueDict

	@staticmethod
	def addFieldInTableByMapping(jsonBindingObject, keyPropertyName, valuePropertyName, inputFeatureClassName, keyPropertyFieldName, valuePropertyURL, isInverse):
		# according to the json object from sparql query which contains the mapping from keyProperty to valueProperty, add field in the Table
		# change the field name if there is already a field which has the same name in table
		# jsonBindingObject: the json object from sparql query which contains the mapping from keyProperty to valueProperty, ex. functionalPropertyJSON
		# keyPropertyName: the name of keyProperty in JSON object, ex. wikidataSub
		# valuePropertyName: the name of valueProperty in JSON object, ex. o
		# keyPropertyFieldName:  the name of the field which stores the value of keyProperty, ex. URL
		# valuePropertyURL: the URL of valueProperty, we use it to get the field name of valueProperty, ex. functionalProperty
		# isInverse: Boolean variable indicates whether the value we get is the subject value or object value of valuePropertyURL

		keyValueDict = Json2Field.buildDictFromJSONToModifyTable(jsonBindingObject, keyPropertyName, valuePropertyName)

		currentValuePropertyName = UTIL.getPropertyName(valuePropertyURL)
		if isInverse == True:
			currentFieldName = "is_" + currentFieldName + "_Of"
		currentFieldName = UTIL.getFieldNameWithTable(currentValuePropertyName, inputFeatureClassName)
		
		arcpy.AddMessage("currentFieldName: {0}".format(currentFieldName))
		if currentFieldName == -1:
			messages.addWarningMessage("The table of current feature class has more than 10 fields for property name {0}.".format(currentValuePropertyName))
		else:
			# add one field for each functional property in input feature class
			fieldType = Json2Field.fieldDataTypeDecide(jsonBindingObject, valuePropertyName)
			arcpy.AddMessage("fieldType: {0}".format(fieldType))
			if fieldType == "TEXT":
				fieldLength = Json2Field.fieldLengthDecide(jsonBindingObject, valuePropertyName)
				arcpy.AddMessage("fieldLength: {0}".format(fieldLength))
				arcpy.AddField_management(inputFeatureClassName, currentFieldName, fieldType, field_length=fieldLength)
			else:
				arcpy.AddField_management(inputFeatureClassName, currentFieldName, fieldType)
			
			# cursor = arcpy.da.UpdateCursor(inputFeatureClassName, [keyPropertyFieldName, currentFieldName])
			cursor = arcpy.UpdateCursor(inputFeatureClassName)
			
			for row in cursor:
				# currentKeyPropertyValue = row[0]
				currentKeyPropertyValue = row.getValue(keyPropertyFieldName)
				if currentKeyPropertyValue in keyValueDict:
					propertyValue = Json2Field.dataTypeCast(keyValueDict[currentKeyPropertyValue], fieldType)
					# row[1] = propertyValue
					row.setValue(currentFieldName, propertyValue)
					cursor.updateRow(row)



	@staticmethod
	def addFieldInMultiKeyTableByMapping(jsonBindingObject, keyPropertyNameList, valuePropertyName, inputFeatureClassName, keyPropertyFieldNameList, valuePropertyURL, isInverse):
		# this function deals with a table with multiple fields as its candidate keys
		# according to the json object from sparql query which contains the mapping from multiple keyProperty to valueProperty, add field in the Table
		# change the field name if there is already a field which has the same name in table
		# jsonBindingObject: the json object from sparql query which contains the mapping from keyProperty to valueProperty, ex. functionalPropertyJSON
		# keyPropertyNameList: a list of the names of keyProperty in JSON object, ex. wikidataSub, s
		# valuePropertyName: the name of valueProperty in JSON object, ex. o
		# keyPropertyFieldNameList:  a list of the names of the fields which stores the value of keyProperty, ex. wikiURL, subDivisionIRI
		# valuePropertyURL: the URL of valueProperty, we use it to get the field name of valueProperty, ex. functionalProperty
		# isInverse: Boolean variable indicates whether the value we get is the subject value or object value of valuePropertyURL

		
		MultiKey = namedtuple("MultiKey", keyPropertyNameList)

		keyValueDict = Json2Field.buildDictFromJSONToModifyMultiKeyTable(jsonBindingObject, keyPropertyNameList, valuePropertyName)

		currentValuePropertyName = UTIL.getPropertyName(valuePropertyURL)
		if isInverse == True:
			currentFieldName = "is_" + currentFieldName + "_Of"
		currentFieldName = UTIL.getFieldNameWithTable(currentValuePropertyName, inputFeatureClassName)
		
		arcpy.AddMessage("currentFieldName: {0}".format(currentFieldName))
		if currentFieldName == -1:
			messages.addWarningMessage("The table of current feature class has more than 10 fields for property name {0}.".format(currentValuePropertyName))
		else:
			# add one field for each functional property in input feature class
			fieldType = Json2Field.fieldDataTypeDecide(jsonBindingObject, valuePropertyName)
			arcpy.AddMessage("fieldType: {0}".format(fieldType))
			if fieldType == "TEXT":
				fieldLength = Json2Field.fieldLengthDecide(jsonBindingObject, valuePropertyName)
				arcpy.AddMessage("fieldLength: {0}".format(fieldLength))
				arcpy.AddField_management(inputFeatureClassName, currentFieldName, fieldType, field_length=fieldLength)
			else:
				arcpy.AddField_management(inputFeatureClassName, currentFieldName, fieldType)
			
			# cursor = arcpy.da.UpdateCursor(inputFeatureClassName, [keyPropertyFieldName, currentFieldName])
			cursor = arcpy.UpdateCursor(inputFeatureClassName)
			
			for row in cursor:
				# currentKeyPropertyValue = row[0]
				MultiKeyValueList = []
				i = 0
				while i < len(keyPropertyFieldNameList):
					MultiKeyValueList.append(row.getValue(keyPropertyFieldNameList[i]))
					i = i + 1
				currentMultiKey = MultiKey._make(MultiKeyValueList)
				# currentKeyPropertyValue = row.getValue(keyPropertyFieldName)
				if currentMultiKey in keyValueDict:
					propertyValue = Json2Field.dataTypeCast(keyValueDict[currentMultiKey], fieldType)
					# row[1] = propertyValue
					row.setValue(currentFieldName, propertyValue)
					cursor.updateRow(row)



	@staticmethod
	def addOrUpdateFieldInTableByMapping(jsonBindingObject, keyPropertyName, valuePropertyName, inputFeatureClassName, keyPropertyFieldName, valuePropertyFieldName):
		# according to the json object from sparql query which contains the mapping from keyProperty to valueProperty, add or update field(if the valueProperty Field already exist in table) in the Table
		# jsonBindingObject: the json object from sparql query which contains the mapping from keyProperty to valueProperty, ex. wikidataIRI -> DBpediaIRI, dbpediaIRIJSON
		# keyPropertyName: the name of keyProperty in JSON object, ex. wikidataSub
		# valuePropertyName: the name of valueProperty in JSON object, ex. DBpediaSub
		# keyPropertyFieldName:  the name of the field which stores the value of keyProperty, ex. URL
		# valuePropertyFieldName: the name of the field which stores the value of valueProperty (its length should be less or equal to 10), ex. DBpediaURL
		# build a wikidata IRI to DBpedia IRI dictionary
		# 
		keyValueDict = Json2Field.buildDictFromJSONToModifyTable(jsonBindingObject, keyPropertyName, valuePropertyName)

		isURLinFieldList = UTIL.isFieldNameInTable(valuePropertyName, inputFeatureClassName)
		fieldType = Json2Field.fieldDataTypeDecide(jsonBindingObject, valuePropertyName)
		arcpy.AddMessage("fieldType: {0}".format(fieldType))
		if isURLinFieldList == False:
			# add one field valuePropertyName, ex. "DBpediaIRI", in input feature class
			if fieldType == "TEXT":
				fieldLength = Json2Field.fieldLengthDecide(jsonBindingObject, valuePropertyName)
				arcpy.AddMessage("fieldLength: {0}".format(fieldLength))
				arcpy.AddField_management(inputFeatureClassName, valuePropertyFieldName, fieldType, field_length=fieldLength)
			else:
				arcpy.AddField_management(inputFeatureClassName, valuePropertyFieldName, fieldType)
		else:
			if fieldType == "TEXT":
				fieldLength = Json2Field.fieldLengthDecide(jsonBindingObject, valuePropertyName)
				fieldList = arcpy.ListFields(inputFeatureClassName)
				for field in fieldList:
					if field.name == valuePropertyFieldName:
						if fieldLength > field.length:
							field.length = fieldLength
						break
		
		# cursor = arcpy.da.UpdateCursor(inputFeatureClassName, [keyPropertyFieldName, valuePropertyFieldName])
		cursor = arcpy.UpdateCursor(inputFeatureClassName)
		for row in cursor:
			# currentKeyPropertyValue = row[0]
			currentKeyPropertyValue = row.getValue(keyPropertyFieldName)
			if currentKeyPropertyValue in keyValueDict:
				currentValuePropertyValue = keyValueDict[currentKeyPropertyValue]
				# row[1] = currentValuePropertyValue
				row.setValue(valuePropertyFieldName, currentValuePropertyValue)
				cursor.updateRow(row)

	@staticmethod
	def fieldLengthDecide(jsonBindingObject, fieldName):
		# This option is only applicable on fields of type text or blob
		fieldType = Json2Field.fieldDataTypeDecide(jsonBindingObject, fieldName)
		if fieldType != "TEXT":
			# you do not need field length
			return -1
		else:
			maxLength = 30
			for jsonItem in jsonBindingObject:
				textLength = len(jsonItem[fieldName]["value"])
				if textLength > maxLength:
					maxLength = textLength

			return maxLength
			


	@staticmethod
	def fieldDataTypeDecide(jsonBindingObject, fieldName):
		# jsonBindingObject: a list object which is jsonObject.json()["results"]["bindings"]
		# fieldName: the name of the property/field in the JSON object thet what to evaluate
		# return the Field data type given a JSONItem for one property, return -1 if the field is about geometry and bnode
		dataTypeSet = Set()
		for jsonItem in jsonBindingObject:
			dataTypeSet.add(Json2Field.getLinkedDataType(jsonItem, fieldName))

		dataTypeList = list(dataTypeSet)
		dataTypeCountDict = dict(zip(dataTypeList, [0]*len(dataTypeList)))

		for jsonItem in jsonBindingObject:
			dataTypeCountDict[Json2Field.getLinkedDataType(jsonItem, fieldName)] += 1

		dataTypeCountOrderDict = OrderedDict(sorted(dataTypeCountDict.items(), key=lambda t: t[1]))
		majorityDataType = next(reversed(dataTypeCountOrderDict))
		majorityFieldDataType = Json2Field.urlDataType2FieldDataType(majorityDataType)
		arcpy.AddMessage("majorityFieldDataType: {0}".format(majorityFieldDataType))

		return majorityFieldDataType

	@staticmethod
	def urlDataType2FieldDataType(urlDataType):
		# urlDataType: url string date geometry int double float bnode
		# get a data type of Linked Data Literal (see getLinkedDataType), return a data type for field in arcgis Table View
		if urlDataType == "uri":
			return "TEXT"
		elif urlDataType == "string":
			return "TEXT"
		elif urlDataType == "date":
			return "DATE"
		elif urlDataType == "geometry":
			return -1
		elif urlDataType == "int":
			return "LONG"
		elif urlDataType == "double":
			return "DOUBLE"
		elif urlDataType == "float":
			return "FLOAT"
		elif urlDataType == "bnode":
			return -1
		else:
			return "TEXT"

	@staticmethod
	def getLinkedDataType(jsonBindingObjectItem, propertyName):
		# according the the property name of this jsonBindingObjectItem, return the meaningful dataType
		rdfDataType = jsonBindingObjectItem[propertyName]["type"]
		if rdfDataType == "uri":
			return "uri"
		elif "literal" in rdfDataType:
			if "datatype" not in jsonBindingObjectItem[propertyName]:
				return "string"
			else:
				specifiedDataType = jsonBindingObjectItem[propertyName]["datatype"]
				if specifiedDataType == "http://www.w3.org/2001/XMLSchema#date":
					return "date"
				elif specifiedDataType == "http://www.openlinksw.com/schemas/virtrdf#Geometry": 
					return "geometry"
				elif specifiedDataType == "http://www.w3.org/2001/XMLSchema#integer" or specifiedDataType == "http://www.w3.org/2001/XMLSchema#nonNegativeInteger":
					return "int"
				elif specifiedDataType == "http://www.w3.org/2001/XMLSchema#double":
					return "double"
				elif specifiedDataType == "http://www.w3.org/2001/XMLSchema#float":
					return "float"
				else:
					return "string"
		elif rdfDataType == "bnode":
			return "bnode"
		else:
			return "string"

	@staticmethod
	def dataTypeCast(fieldValue, fieldDataType):
		# according to the field data type, cast the data into corresponding data type
		if fieldDataType == "TEXT":
			return fieldValue
		elif fieldDataType == "DATE":

			return fieldValue
		elif fieldDataType == "LONG":
			return int(fieldValue)
		elif fieldDataType == "DOUBLE":
			return Decimal(fieldValue)
		elif fieldDataType == "FLOAT":
			return float(fieldValue)



