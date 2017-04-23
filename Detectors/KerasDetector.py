import sys, os
from Detector import Detector
import itertools
from ExampleBuilders.KerasExampleBuilder import KerasExampleBuilder
import numpy as np
import xml.etree.ElementTree as ET
import Utils.ElementTreeUtils as ETUtils
from Core.IdSet import IdSet
import Utils.Parameters
import gzip
import json
from keras.layers import Input, Dense, Conv2D, MaxPooling2D, UpSampling2D
from keras.models import Model, Sequential
from keras.layers.normalization import BatchNormalization
from keras.layers.core import Activation, Reshape, Permute
from keras.optimizers import SGD

class KerasDetector(Detector):
    """
    The KerasDetector replaces the default SVM-based learning with a pipeline where
    sentences from the XML corpora are converted into adjacency matrix examples which
    are used to train the Keras model defined in the KerasDetector.
    """

    def __init__(self):
        Detector.__init__(self)
        self.STATE_COMPONENT_TRAIN = "COMPONENT_TRAIN"
        self.tag = "keras-"
        self.exampleBuilder = KerasExampleBuilder
        self.matrices = None
        self.arrays = None
    
    ###########################################################################
    # Main Pipeline Interface
    ###########################################################################
    
    def train(self, trainData=None, optData=None, model=None, combinedModel=None, exampleStyle=None, 
              classifierParameters=None, parse=None, tokenization=None, task=None, fromStep=None, toStep=None,
              workDir=None):
        self.initVariables(trainData=trainData, optData=optData, model=model, combinedModel=combinedModel, exampleStyle=exampleStyle, classifierParameters=classifierParameters, parse=parse, tokenization=tokenization)
        self.setWorkDir(workDir)
        self.enterState(self.STATE_TRAIN, ["ANALYZE", "EXAMPLES", "MODEL"], fromStep, toStep)
        if self.checkStep("ANALYZE"):
            # General training initialization done at the beginning of the first state
            self.model = self.initModel(self.model, [("exampleStyle", self.tag+"example-style"), ("classifierParameters", self.tag+"classifier-parameters-train")])
            self.saveStr(self.tag+"parse", parse, self.model)
            if task != None:
                self.saveStr(self.tag+"task", task, self.model)
            # Perform structure analysis
            self.structureAnalyzer.analyze([optData, trainData], self.model)
            print >> sys.stderr, self.structureAnalyzer.toString()
        self.styles = Utils.Parameters.get(exampleStyle)
        self.model = self.openModel(model, "a") # Devel model already exists, with ids etc
        exampleFiles = {"devel":self.workDir+self.tag+"opt-examples.json.gz", "train":self.workDir+self.tag+"train-examples.json.gz"}
        if self.checkStep("EXAMPLES"): # Generate the adjacency matrices
            self.buildExamples(self.model, ["devel", "train"], [optData, trainData], [exampleFiles["devel"], exampleFiles["train"]], saveIdsToModel=True)
        if self.checkStep("MODEL"): # Define and train the Keras model
            self.defineModel()
            self.fitModel(exampleFiles)
        if workDir != None:
            self.setWorkDir("")
        self.arrays = None
        self.exitState()
        
    ###########################################################################
    # Main Pipeline Steps
    ###########################################################################
    
    def buildExamples(self, model, setNames, datas, outputs, golds=[], exampleStyle=None, saveIdsToModel=False, parse=None):
        """
        Runs the KerasExampleBuilder for the input XML files and saves the generated adjacency matrices
        into JSON files.
        """
        if exampleStyle == None:
            exampleStyle = model.getStr(self.tag+"example-style")
        if parse == None:
            parse = self.getStr(self.tag+"parse", model)
        self.structureAnalyzer.load(model)
        self.exampleBuilder.structureAnalyzer = self.structureAnalyzer
        self.matrices = {} # For the Python-dictionary matrices generated by KerasExampleBuilder
        modelChanged = False
        # Make example for all input files
        for setName, data, output, gold in itertools.izip_longest(setNames, datas, outputs, golds, fillvalue=None):
            print >> sys.stderr, "Example generation for set", setName, "to file", output
            if saveIdsToModel:
                modelChanged = True
            builder = self.exampleBuilder.run(data, output, parse, None, exampleStyle, model.get(self.tag+"ids.classes", 
                True), model.get(self.tag+"ids.features", True), gold, False, saveIdsToModel,
                structureAnalyzer=self.structureAnalyzer)
            model.addStr("dimSourceFeatures", str(len(builder.featureSet.Ids)))
            model.addStr("dimTargetFeatures", str(len(builder.classSet.Ids)))
            model.addStr("dimMatrix", str(builder.dimMatrix))
            examples =  {"source":builder.sourceMatrices, "target":builder.targetMatrices, "tokens":builder.tokenLists, "setName":setName}
            print >> sys.stderr, "Saving examples to", output
            self.saveJSON(output, examples)
            self.matrices[setName] = examples
            if "html" in self.styles:
                self.matricesToHTML(model, self.matrices[setName], output + ".html", int(self.styles["html"]))
                    
        if hasattr(self.structureAnalyzer, "typeMap") and model.mode != "r":
            print >> sys.stderr, "Saving StructureAnalyzer.typeMap"
            self.structureAnalyzer.save(model)
            modelChanged = True
        if modelChanged:
            model.save()
    
    def defineModel(self):
        """
        Defines the Keras model and compiles it.
        """
        dimSourceFeatures = int(self.model.getStr("dimSourceFeatures")) # Number of channels in the source matrix
        dimTargetFeatures = int(self.model.getStr("dimTargetFeatures")) # Number of channels in the target matrix
        dimMatrix = int(self.model.getStr("dimMatrix")) # The width/height of both the source and target matrix
        
        print >> sys.stderr, "Defining model"
        inputShape = Input(shape=(dimMatrix, dimMatrix, dimSourceFeatures))
        #x = Conv2D(16, (1, 9), activation='relu', padding='same')(inputShape)
        #x = Conv2D(16, (9, 1), activation='relu', padding='same')(x)
        #x = MaxPooling2D((2, 2))(x)
        x = Dense(18)(inputShape)
        x = Dense(18)(x)
        x = Conv2D(dimTargetFeatures, (1, 1), activation='softmax', padding='same')(x)
        #x = UpSampling2D((2, 2))(x)
        #x = Activation('softmax')(x)
        self.kerasModel = Model(inputShape, x)
        self.kerasModel.compile(optimizer="adadelta", loss='categorical_crossentropy', metrics=['accuracy'])
        
#         x = Conv2D(4, (3, 3), activation='relu', padding='same')(inputShape)
#         x = MaxPooling2D((2, 2))(x)
#         x = Conv2D(4, (3, 3), activation='relu', padding='same')(x)
#         x = UpSampling2D((2, 2))(x)
#         x = Conv2D(dimTargetFeatures, (3, 3), activation='relu', padding='same')(x)
#         self.kerasModel = Model(inputShape, x)
#         self.kerasModel.compile(optimizer="adadelta", loss='categorical_crossentropy', metrics=['accuracy'])
        
#         kernel = 3
#         encoding_layers = [
#             Conv2D(16, (kernel, kernel), padding='same', input_shape=(dimMatrix, dimMatrix, dimSourceFeatures)),
#             BatchNormalization(),
#             Activation('relu'),
#             Conv2D(64, (kernel, kernel), padding='same'),
#             BatchNormalization(),
#             Activation('relu'),
#             MaxPooling2D()]
#     
#         decoding_layers = [
#             UpSampling2D(),
#             Conv2D(dimTargetFeatures, (kernel, kernel), padding='same'),
#             BatchNormalization(),
#             Activation('relu'),
#             Conv2D(dimTargetFeatures, (kernel, kernel), padding='same'),
#             BatchNormalization(),
#             Activation('relu'),
#             Conv2D(dimTargetFeatures, (kernel, kernel), padding='same'),
#             BatchNormalization(),
#             Activation('relu')]
#         
#         self.kerasModel = Sequential()
#         for l in encoding_layers + decoding_layers:
#             self.kerasModel.add(l)
#         
#         self.kerasModel.add(Activation('softmax'))
#         
#         print >> sys.stderr, "Compiling model"
#         optimizer = SGD(lr=0.001, momentum=0.9, decay=0.0005, nesterov=False)
#         self.kerasModel.compile(optimizer=optimizer, loss='categorical_crossentropy', metrics=['accuracy'])
        
        # Various attempts at neural networks: ##########################################        
        
        #         x = Conv2D(8, (4, 4), activation='relu', padding='same')(inputShape)
        #         #x = UpSampling2D((2, 2))(x)
        #         decoded = Conv2D(dimTargetFeatures, (3, 3), activation='sigmoid', padding='same')(x)
         
        #         x = Conv2D(16, (3, 3), activation='relu', padding='same')(inputShape)
        #         x = MaxPooling2D((2, 2), padding='same')(x)
        #         x = Conv2D(8, (3, 3), activation='relu', padding='same')(x)
        #         x = MaxPooling2D((2, 2), padding='same')(x)
        #         x = Conv2D(8, (3, 3), activation='relu', padding='same')(x)
        #         encoded = MaxPooling2D((2, 2), padding='same')(x)
        #          
        #         # at this point the representation is (4, 4, 8) i.e. 128-dimensional
        #          
        #         x = Conv2D(8, (3, 3), activation='relu', padding='same')(encoded)
        #         x = UpSampling2D((2, 2))(x)
        #         x = Conv2D(8, (3, 3), activation='relu', padding='same')(x)
        #         x = UpSampling2D((2, 2))(x)
        #         x = Conv2D(16, (3, 3), activation='relu')(x)
        #         x = UpSampling2D((2, 2))(x)
        #         decoded = Conv2D(dimFeatures, (3, 3), activation='sigmoid', padding='same')(x)
        
        
        #x = Conv2D(16, (3, 3), padding='same')(inputShape)
        #output = Conv2D(dimTargetFeatures, (1, 1), activation='tanh', padding='same')(x)
        
        #x = Dense(100)(inputShape)
        #x = Dense(18)(x)
        
        #x = Conv2D(100, (5, 5), padding='same')(inputShape)
        #x = Conv2D(100, (3, 3), padding='same')(x)
        #x = Conv2D(100, (2, 2), padding='same')(x)
        #x = Conv2D(dimTargetFeatures, (1, 1), padding='same')(x)
        
        #self.kerasModel.compile(optimizer='adadelta', loss='binary_crossentropy', metrics=['accuracy'])

    def fitModel(self, exampleFiles):
        """
        Fits the compiled Keras model to the adjacency matrix examples. The model is trained on the
        train set, validated on the devel set and finally the devel set is predicted using the model.
        """
        if self.matrices == None: # If program is run from the TRAIN.MODEL step matrices are loaded from files
            self.matrices = {}
            for setName in exampleFiles:
                print >> sys.stderr, "Loading dataset", setName, "from", exampleFiles[setName]
                self.matrices[setName] = self.loadJSON(exampleFiles[setName])
        if self.arrays == None: # The Python dictionary matrices are converted into dense Numpy arrays
            self.vectorizeMatrices(self.model)
        
        print >> sys.stderr, "Fitting model"
        #es_cb = EarlyStopping(monitor='val_loss', patience=10, verbose=1)
        #cp_cb = ModelCheckpoint(filepath=self.workDir + self.tag + 'model.hdf5', save_best_only=True, verbose=1)
        self.kerasModel.fit(self.arrays["train"]["source"], self.arrays["train"]["target"],
            epochs=100 if not "epochs" in self.styles else int(self.styles["epochs"]),
            batch_size=128,
            shuffle=True,
            validation_data=(self.arrays["devel"]["source"], self.arrays["devel"]["target"]))
            #callbacks=[es_cb])#, cp_cb])
        
        print >> sys.stderr, "Predicting devel examples"
        predictions = self.kerasModel.predict(self.arrays["devel"]["source"], 128, 1)
        
        # The predicted matrices are saved as an HTML heat map
        predMatrices = self.loadJSON(exampleFiles["devel"])
        predMatrices["predicted"] = self.devectorizePredictions(predictions)
        if "save_predictions" in self.styles:
            print >> sys.stderr, "Saving predictions to", self.workDir + self.tag + "devel-predictions.json.gz"
            self.saveJSON(self.workDir + self.tag + "devel-predictions.json.gz", predMatrices)
        if "html" in self.styles:
            self.matricesToHTML(self.model, predMatrices, self.workDir + self.tag + "devel-predictions.html", int(self.styles["html"]))
        
        # For now the training ends here, later the predicted matrices should be converted back to XML events
        sys.exit()
    
    ###########################################################################
    # HTML Table visualization
    ###########################################################################
    
    def matrixToTable(self, matrix, tokens):
        """
        Converts a single Python dictionary adjacency matrix into an HTML table structure.
        """
        matrixRange = range(len(matrix) + 1)
        table = ET.Element('table', {"border":"1"})
        for i in matrixRange:
            tr = ET.SubElement(table, 'tr')
            for j in matrixRange:
                td = ET.SubElement(tr, 'td')
                if i == 0 or j == 0:
                    if i != 0 and i > 0 and i <= len(tokens): td.text = tokens[i - 1]
                    elif j != 0 and j > 0 and j <= len(tokens): td.text = tokens[j - 1]
                else:
                    if i == j: # This element is on the diagonal
                        td.set("style", "font-weight:bold;")
                    features = matrix[i - 1][j - 1]
                    if "color" in features: # The 'color' is not a real feature, but rather defines this table element's background color
                        td.set("bgcolor", features["color"])
                    featureNames = [x for x in features if x != "color"]
                    featureNames.sort()
                    td.text = ",".join(featureNames)
                    td.set("weights", ",".join([x + "=" + str(features[x]) for x in featureNames]))
        return table
    
    def matricesToHTML(self, model, data, filePath, cutoff=None):
        """
        Saves the source (features), target (labels) and predicted adjacency matrices
        for a list of sentences as HTML tables.
        """
        root = ET.Element('html')     
        sourceMatrices = data["source"]
        targetMatrices = data["target"]
        predMatrices = data.get("predicted")
        tokenLists = data["tokens"]
        for i in range(len(sourceMatrices)):
            if cutoff is not None and i >= cutoff:
                break
            ET.SubElement(root, "h3").text = str(i) + ": " + " ".join(tokenLists[i])
            ET.SubElement(root, "p").text = "Source"
            root.append(self.matrixToTable(sourceMatrices[i], tokenLists[i]))
            ET.SubElement(root, "p").text = "Target"
            root.append(self.matrixToTable(targetMatrices[i], tokenLists[i]))
            if predMatrices is not None:
                ET.SubElement(root, "p").text = "Predicted"
                root.append(self.matrixToTable(predMatrices[i], tokenLists[i]))
        print >> sys.stderr, "Writing adjacency matrix visualization to", os.path.abspath(filePath)
        ETUtils.write(root, filePath)
        
    def clamp(self, value, lower, upper):
        return max(lower, min(value, upper))
    
    def getColor(self, value):
        r = self.clamp(int((1.0 - value) * 255.0), 0, 255)
        g = self.clamp(int(value * 255.0), 0, 255)
        b = 0
        return '#%02x%02x%02x' % (r, g, b)
    
    ###########################################################################
    # Serialization
    ###########################################################################
    
    def saveJSON(self, filePath, data):
        with gzip.open(filePath, "wt") as f:
            json.dump(data, f, indent=2)
    
    def loadJSON(self, filePath):
        with gzip.open(filePath, "rt") as f:
            return json.load(f)
    
    ###########################################################################
    # Vectorization
    ###########################################################################
    
    def devectorizePredictions(self, predictions):
        """
        Converts a dense Numpy array of [examples][width][height][features] into
        the corresponding Python list matrices where features are stored in a key-value
        dictionary.
        """
        targetIds = IdSet(filename=self.model.get(self.tag+"ids.classes"), locked=True)
        dimMatrix = int(self.model.getStr("dimMatrix"))
        rangeMatrix = range(dimMatrix)
        labels = np.argmax(predictions, axis=-1)
        values = np.max(predictions, axis=-1)
        minValue = np.min(values)
        maxValue = np.max(values)
        valRange = maxValue - minValue
        print "MINMAX", minValue, maxValue
        devectorized = []
        for exampleIndex in range(predictions.shape[0]):
            #print predictions[exampleIndex]
            devectorized.append([])
            for i in rangeMatrix:
                devectorized[-1].append([])
                for j in rangeMatrix:
                    features = {}
                    devectorized[-1][-1].append(features)
                    maxFeature = labels[exampleIndex][i][j]
                    features[targetIds.getName(maxFeature)] = float(values[exampleIndex][i][j])
                    features["color"] = self.getColor((values[exampleIndex][i][j] - minValue) / valRange)
        return devectorized
    
    def vectorizeMatrices(self, model):
        """
        Converts the Python input matrices of the form [examples][width][height]{features} into
        corresponding dense Numpy arrays.
        """
        self.arrays = {}
        sourceIds = IdSet(filename=model.get(self.tag+"ids.features"), locked=True)
        targetIds = IdSet(filename=model.get(self.tag+"ids.classes"), locked=True)
        dimSourceFeatures = int(model.getStr("dimSourceFeatures"))
        dimTargetFeatures = int(model.getStr("dimTargetFeatures"))
        dimMatrix = int(model.getStr("dimMatrix"))
        rangeMatrix = range(dimMatrix)
        dataSets = [(x, self.matrices[x]) for x in sorted(self.matrices.keys())]
        self.matrices = None
        while dataSets:
            dataSetName, dataSetValue = dataSets.pop()
            print >> sys.stderr, "Vectorizing dataset", dataSetName
            sourceMatrices = dataSetValue["source"]
            targetMatrices = dataSetValue["target"]
            assert len(sourceMatrices) == len(targetMatrices)
            numExamples = len(sourceMatrices)
            sourceArrays = np.zeros((numExamples, dimMatrix, dimMatrix, dimSourceFeatures), dtype=np.float32)
            targetArrays = np.zeros((numExamples, dimMatrix, dimMatrix, dimTargetFeatures), dtype=np.float32)
            for exampleIndex in range(numExamples):
                sourceArray = sourceArrays[exampleIndex] #sourceArray = np.zeros((dimMatrix, dimMatrix, dimFeatures), dtype=np.float32)
                targetArray = targetArrays[exampleIndex] #targetArray = np.zeros((dimMatrix, dimMatrix, dimFeatures), dtype=np.float32)
                sourceMatrix = sourceMatrices.pop(0) #[exampleIndex]
                targetMatrix = targetMatrices.pop(0) #[exampleIndex]
                for matrix, array, ids in [(sourceMatrix, sourceArray, sourceIds), (targetMatrix, targetArray, targetIds)]:
                    for i in rangeMatrix:
                        for j in rangeMatrix:
                            features = matrix[i][j]
                            #print features
                            for featureName in features:
                                array[i][j][ids.getId(featureName)] = features[featureName]
            self.arrays[dataSetName] = {"source":sourceArrays, "target":targetArrays}