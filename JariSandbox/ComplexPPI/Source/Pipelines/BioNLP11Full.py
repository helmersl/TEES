# Optimize parameters for event detection and produce event and trigger model files

# most imports are defined in Pipeline
from Pipeline import *
import sys, os
import STFormat.ConvertXML

def updateModel(modelPath, linkName):
    if os.path.exists(linkName):
        os.remove(linkName)
    if os.path.exists(modelPath):
        print "Linking to best model", modelPath
        os.symlink(modelPath, linkName)
        return linkName
    else:
        return None

def getA2FileTag(task, subTask):
    if task == "REL":
        return "rel"
    return "a2"

from optparse import OptionParser
optparser = OptionParser()
optparser.add_option("-e", "--test", default=Settings.DevelFile, dest="testFile", help="Test file in interaction xml")
optparser.add_option("-r", "--train", default=Settings.TrainFile, dest="trainFile", help="Train file in interaction xml")
optparser.add_option("-o", "--output", default=None, dest="output", help="output directory")
optparser.add_option("-a", "--task", default="1", dest="task", help="task number")
optparser.add_option("-p", "--parse", default="split-McClosky", dest="parse", help="Parse XML element name")
optparser.add_option("-t", "--tokenization", default=None, dest="tokenization", help="Tokenization XML element name")
optparser.add_option("-m", "--mode", default="BOTH", dest="mode", help="MODELS (recalculate SVM models), GRID (parameter grid search) or BOTH")
# Classifier
optparser.add_option("-c", "--classifier", default="Cls", dest="classifier", help="")
optparser.add_option("--csc", default="", dest="csc", help="")
# Example builders
optparser.add_option("-f", "--triggerExampleBuilder", default="GeneralEntityTypeRecognizerGztr", dest="triggerExampleBuilder", help="")
optparser.add_option("-g", "--edgeExampleBuilder", default="MultiEdgeExampleBuilder", dest="edgeExampleBuilder", help="")
# Feature params
optparser.add_option("--triggerStyle", default=None, dest="triggerStyle", help="")
optparser.add_option("--edgeStyle", default=None, dest="edgeStyle", help="")
# Id sets
optparser.add_option("-v", "--triggerIds", default=None, dest="triggerIds", help="Trigger detector SVM example class and feature id file stem (files = STEM.class_names and STEM.feature_names)")
optparser.add_option("-w", "--edgeIds", default=None, dest="edgeIds", help="Edge detector SVM example class and feature id file stem (files = STEM.class_names and STEM.feature_names)")
# Parameters to optimize
optparser.add_option("-x", "--triggerParams", default="1000,5000,10000,20000,50000,80000,100000,150000,180000,200000,250000,300000,350000,500000,1000000", dest="triggerParams", help="Trigger detector c-parameter values")
optparser.add_option("-y", "--recallAdjustParams", default="0.5,0.6,0.65,0.7,0.85,1.0,1.1,1.2", dest="recallAdjustParams", help="Recall adjuster parameter values")
optparser.add_option("-z", "--edgeParams", default="5000,7500,10000,20000,25000,28000,50000,60000,65000", dest="edgeParams", help="Edge detector c-parameter values")
# Shared task evaluation
#optparser.add_option("-s", "--sharedTask", default=True, action="store_false", dest="sharedTask", help="Do Shared Task evaluation")
optparser.add_option("--clearAll", default=False, action="store_true", dest="clearAll", help="Delete all files")
optparser.add_option("-u", "--unmerging", default=False, action="store_true", dest="unmerging", help="SVM unmerging")
(options, args) = optparser.parse_args()

# Check options
assert options.mode in ["MODELS", "FINAL", "BOTH", "GRID"]
assert options.output != None
assert options.task in ["OLD.1", "OLD.2", "CO", "REL", "GE", "EPI", "ID"]
subTask = 2
if "." in options.task:
    options.task, subTask = options.task.split(".")
    subTask = int(subTask)

exec "CLASSIFIER = " + options.classifier

# Main settings
PARSE=options.parse
TOK=options.tokenization
PARSE_TAG = PARSE
TRAIN_FILE = options.trainFile
TEST_FILE = options.testFile

# Example generation parameters
if options.edgeStyle != None:
    EDGE_FEATURE_PARAMS="style:"+options.edgeStyle
else:
    if options.task in ["OLD", "GE"]:
        EDGE_FEATURE_PARAMS="style:trigger_features,typed,directed,no_linear,entities,genia_limits,noMasking,maxFeatures"
    else:
        EDGE_FEATURE_PARAMS="style:trigger_features,typed,directed,no_linear,entities,noMasking,maxFeatures"
if options.triggerStyle != None:  
    TRIGGER_FEATURE_PARAMS="style:"+options.triggerStyle #"style:typed"
else:
    TRIGGER_FEATURE_PARAMS="style:typed"
UNMERGING_IDS = "unmerging-ids"
UNMERGING_CLASSIFIER_PARAMS="c:" + options.triggerParams
UNMERGING_FEATURE_PARAMS="style:typed"

boosterParams = [float(i) for i in options.recallAdjustParams.split(",")]
if options.task == "CO":
    BINARY_RECALL_MODE = True
else:
    BINARY_RECALL_MODE = False

# These commands will be in the beginning of most pipelines
WORKDIR=options.output

# CSC Settings
CSC_WORKDIR = os.path.join("CSCConnection",WORKDIR.lstrip("/"))
if "," in options.csc:
    options.csc = options.csc.split(",")
else:
    options.csc = [options.csc]
if options.clearAll and "clear" not in options.csc:
    options.csc.append("clear")
if "local" not in options.csc:
    CSC_CLEAR = False
    if "clear" in options.csc: CSC_CLEAR = True
    if "louhi" in options.csc:
        CSC_ACCOUNT="jakrbj@louhi.csc.fi"
    else:
        CSC_ACCOUNT="jakrbj@murska.csc.fi"

# Start logging
workdir(WORKDIR, options.clearAll) # Select a working directory, optionally remove existing files
log() # Start logging into a file in working directory

if subTask != None:
    print >> sys.stderr, "Task:", options.task + "." + str(subTask)
else:
    print >> sys.stderr, "Task:", options.task
print >> sys.stderr, "Edge params:", EDGE_FEATURE_PARAMS
print >> sys.stderr, "Trigger params:", TRIGGER_FEATURE_PARAMS
TRIGGER_EXAMPLE_BUILDER = eval(options.triggerExampleBuilder)
EDGE_EXAMPLE_BUILDER = eval(options.edgeExampleBuilder)

# Pre-calculate all the required SVM models
TRIGGER_IDS = "trigger-ids"
EDGE_IDS = "edge-ids"
TRIGGER_TRAIN_EXAMPLE_FILE = "trigger-train-examples-"+PARSE_TAG
TRIGGER_TEST_EXAMPLE_FILE = "trigger-test-examples-"+PARSE_TAG
TRIGGER_CLASSIFIER_PARAMS="c:" + options.triggerParams
EDGE_TRAIN_EXAMPLE_FILE = "edge-train-examples-"+PARSE_TAG
EDGE_TEST_EXAMPLE_FILE = "edge-test-examples-"+PARSE_TAG
EDGE_CLASSIFIER_PARAMS="c:" + options.edgeParams
if options.mode in ["BOTH", "MODELS"]:
    if False:
        if options.triggerIds != None:
            TRIGGER_IDS = copyIdSetsToWorkdir(options.triggerIds)
        if options.edgeIds != None:
            EDGE_IDS = copyIdSetsToWorkdir(options.edgeIds)
        
        ###############################################################################
        # Trigger example generation
        ###############################################################################
        print >> sys.stderr, "Trigger examples for parse", PARSE_TAG   
        TRIGGER_EXAMPLE_BUILDER.run(TEST_FILE, TRIGGER_TEST_EXAMPLE_FILE, PARSE, TOK, TRIGGER_FEATURE_PARAMS, TRIGGER_IDS)
        TRIGGER_EXAMPLE_BUILDER.run(TRAIN_FILE, TRIGGER_TRAIN_EXAMPLE_FILE, PARSE, TOK, TRIGGER_FEATURE_PARAMS, TRIGGER_IDS)
        
        ###############################################################################
        # Trigger models
        ###############################################################################
        print >> sys.stderr, "Trigger models for parse", PARSE_TAG
        c = None
        if "local" not in options.csc:
            c = CSCConnection(CSC_WORKDIR+"/trigger-models", CSC_ACCOUNT, CSC_CLEAR)
        optimize(CLASSIFIER, Ev, TRIGGER_TRAIN_EXAMPLE_FILE, TRIGGER_TEST_EXAMPLE_FILE,\
            TRIGGER_IDS+".class_names", TRIGGER_CLASSIFIER_PARAMS, "trigger-models", None, c, False, steps="SUBMIT")
        
        ###############################################################################
        # Edge example generation
        ###############################################################################
        print >> sys.stderr, "Edge examples for parse", PARSE_TAG  
        EDGE_EXAMPLE_BUILDER.run(TEST_FILE, EDGE_TEST_EXAMPLE_FILE, PARSE, TOK, EDGE_FEATURE_PARAMS, EDGE_IDS)
        EDGE_EXAMPLE_BUILDER.run(TRAIN_FILE, EDGE_TRAIN_EXAMPLE_FILE, PARSE, TOK, EDGE_FEATURE_PARAMS, EDGE_IDS)
        
        ###############################################################################
        # Edge models
        ###############################################################################
        print >> sys.stderr, "Edge models for parse", PARSE_TAG
        c = None
        if "local" not in options.csc:
            c = CSCConnection(CSC_WORKDIR+"/edge-models", CSC_ACCOUNT, CSC_CLEAR)
        optimize(CLASSIFIER, Ev, EDGE_TRAIN_EXAMPLE_FILE, EDGE_TEST_EXAMPLE_FILE,\
            EDGE_IDS+".class_names", EDGE_CLASSIFIER_PARAMS, "edge-models", None, c, False, steps="SUBMIT")
else:
    # New feature ids may have been defined during example generation, 
    # so use for the grid search the id sets copied to WORKDIR during 
    # model generation. The set files will have the same names as the files 
    # they are copied from
    if options.triggerIds != None:
        TRIGGER_IDS = os.path.basename(options.triggerIds)
    if options.edgeIds != None:
        EDGE_IDS = os.path.basename(options.edgeIds)
    UNMERGING_IDS = "unmerging-ids"


###############################################################################
# Classification with recall boosting
###############################################################################
if options.mode in ["BOTH", "FINAL", "GRID"]:
    if options.mode != "GRID":
        c = None
        if "local" not in options.csc:
            c = CSCConnection(CSC_WORKDIR+"/trigger-models", CSC_ACCOUNT, CSC_CLEAR)
        bestTriggerModel = optimize(CLASSIFIER, Ev, TRIGGER_TRAIN_EXAMPLE_FILE, TRIGGER_TEST_EXAMPLE_FILE,\
            TRIGGER_IDS+".class_names", TRIGGER_CLASSIFIER_PARAMS, "trigger-models", None, c, True, steps="RESULTS")[1]
        bestTriggerModel = updateModel(bestTriggerModel, "best-trigger-model")
        c = None
        if "local" not in options.csc:
            c = CSCConnection(CSC_WORKDIR+"/edge-models", CSC_ACCOUNT, CSC_CLEAR)
        bestEdgeModel = optimize(CLASSIFIER, Ev, EDGE_TRAIN_EXAMPLE_FILE, EDGE_TEST_EXAMPLE_FILE,\
            EDGE_IDS+".class_names", EDGE_CLASSIFIER_PARAMS, "edge-models", None, c, True, steps="RESULTS")[1]
        bestEdgeModel = updateModel(bestEdgeModel, "best-edge-model")
    else:
        bestTriggerModel = "best-trigger-model"
        bestEdgeModel = "best-edge-model"
        #bestUnmergingModel = "best-unmerging-model"

    ###############################################################################
    # Unmerging learning
    ###############################################################################
    if options.unmerging:
        print >> sys.stderr, "Unmerging models"
        # Self-classified train data for unmerging
        TRIGGER_EXAMPLE_BUILDER.run(TRAIN_FILE, "unmerging-extra-trigger-examples", PARSE, TOK, TRIGGER_FEATURE_PARAMS, TRIGGER_IDS)
        if bestTriggerModel != None: print >> sys.stderr, "best-trigger-model=", os.path.realpath("best-trigger-model")
        CLASSIFIER.test("unmerging-extra-trigger-examples", bestTriggerModel, "unmerging-extra-trigger-classifications")
        xml = BioTextExampleWriter.write("unmerging-extra-trigger-examples", "unmerging-extra-trigger-classifications", TRAIN_FILE, "unmerging-extra-triggers.xml", TRIGGER_IDS+".class_names", PARSE, TOK)
        EDGE_EXAMPLE_BUILDER.run(xml, "unmerging-extra-edge-examples", PARSE, TOK, EDGE_FEATURE_PARAMS, EDGE_IDS)
        if bestEdgeModel != None: print >> sys.stderr, "best-edge-model=", os.path.realpath("best-edge-model")
        CLASSIFIER.test("unmerging-extra-edge-examples", bestEdgeModel, "unmerging-extra-edge-classifications")
        evaluator = Ev.evaluate("unmerging-extra-edge-examples", "unmerging-extra-edge-classifications", TRIGGER_IDS+".class_names")
        xml = BioTextExampleWriter.write("unmerging-extra-edge-examples", "unmerging-extra-edge-trigger-classifications", xml, "unmerging-extra.xml", TRIGGER_IDS+".class_names", PARSE, TOK)
        EvaluateInteractionXML.run(Ev, xml, TRAIN_FILE, PARSE, TOK)
        ###############################################################################
        # Unmerging example generation
        ###############################################################################
        UNMERGING_TRAIN_EXAMPLE_FILE = "unmerging-train-examples-"+PARSE_TAG
        UNMERGING_TEST_EXAMPLE_FILE = "unmerging-test-examples-"+PARSE_TAG
        print >> sys.stderr, "Unmerging examples for parse", PARSE_TAG
        GOLD_TEST_FILE = TEST_FILE.replace("-nodup", "")
        GOLD_TRAIN_FILE = TRAIN_FILE.replace("-nodup", "")
        UnmergingExampleBuilder.run(TEST_FILE, GOLD_TEST_FILE, UNMERGING_TEST_EXAMPLE_FILE, PARSE, TOK, UNMERGING_FEATURE_PARAMS, UNMERGING_IDS)
        UnmergingExampleBuilder.run(TRAIN_FILE, GOLD_TRAIN_FILE, UNMERGING_TRAIN_EXAMPLE_FILE, PARSE, TOK, UNMERGING_FEATURE_PARAMS, UNMERGING_IDS)
        UnmergingExampleBuilder.run("unmerging-extra.xml", GOLD_TRAIN_FILE, UNMERGING_TRAIN_EXAMPLE_FILE, PARSE, TOK, UNMERGING_FEATURE_PARAMS, UNMERGING_IDS, append=True)
        #UnmergingExampleBuilder.run("/home/jari/biotext/EventExtension/TrainSelfClassify/test-predicted-edges.xml", GOLD_TRAIN_FILE, UNMERGING_TRAIN_EXAMPLE_FILE, PARSE, TOK, UNMERGING_FEATURE_PARAMS, UNMERGING_IDS, append=True)
        ###############################################################################
        # Unmerging models
        ###############################################################################
        print >> sys.stderr, "Unmerging models for parse", PARSE_TAG
        c = None
        if "local" not in options.csc: c = CSCConnection(CSC_WORKDIR+"/unmerging-models", CSC_ACCOUNT, CSC_CLEAR)
        bestUnmergingModel = optimize(CLASSIFIER, Ev, UNMERGING_TRAIN_EXAMPLE_FILE, UNMERGING_TEST_EXAMPLE_FILE,\
                UNMERGING_IDS+".class_names", UNMERGING_CLASSIFIER_PARAMS, "unmerging-models", None, c, False, steps="BOTH")
        bestUnmergingModel = updateModel(bestUnmergingModel, "best-unmerging-model")
    
    print >> sys.stderr, "Booster parameter search"
    # Build trigger examples
    TRIGGER_EXAMPLE_BUILDER.run(TEST_FILE, "test-trigger-examples", PARSE, TOK, TRIGGER_FEATURE_PARAMS, TRIGGER_IDS)
    CLASSIFIER.test("test-trigger-examples", bestTriggerModel, "test-trigger-classifications")
    if bestTriggerModel != None:
        print >> sys.stderr, "best-trigger-model=", os.path.realpath("best-trigger-model")
    evaluator = Ev.evaluate("test-trigger-examples", "test-trigger-classifications", TRIGGER_IDS+".class_names")
    xml = BioTextExampleWriter.write("test-trigger-examples", "test-trigger-classifications", TEST_FILE, "trigger-pred-best.xml", TRIGGER_IDS+".class_names", PARSE, TOK)
    
    count = 0
    bestResults = None
    for boost in boosterParams:
        print >> sys.stderr, "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        print >> sys.stderr, "Processing params", str(count) + "/" + str(len(boosterParams)), boost
        print >> sys.stderr, "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        
        # Boost
        xml = RecallAdjust.run("trigger-pred-best.xml", boost, None, binary=BINARY_RECALL_MODE)
        xml = ix.splitMergedElements(xml, None)
        xml = ix.recalculateIds(xml, None, True)
        
        # Build edge examples
        EDGE_EXAMPLE_BUILDER.run(xml, "test-edge-examples", PARSE, TOK, EDGE_FEATURE_PARAMS, EDGE_IDS)
        # Classify with pre-defined model
        if bestEdgeModel != None:
            print >> sys.stderr, "best-edge-model=", os.path.realpath("best-edge-model")
        CLASSIFIER.test("test-edge-examples", bestEdgeModel, "test-edge-classifications")
        # Write to interaction xml
        evaluator = Ev.evaluate("test-edge-examples", "test-edge-classifications", EDGE_IDS+".class_names")
        if evaluator.getData().getTP() + evaluator.getData().getFP() > 0:
            #xml = ExampleUtils.writeToInteractionXML("test-edge-examples", "test-edge-classifications", xml, None, EDGE_IDS+".class_names", PARSE, TOK)
            xml = BioTextExampleWriter.write("test-edge-examples", "test-edge-classifications", xml, None, EDGE_IDS+".class_names", PARSE, TOK)
            xml = ix.splitMergedElements(xml, None)
            xml = ix.recalculateIds(xml, "flat-" + str(boost) + ".xml", True)
            
            # EvaluateInteractionXML differs from the previous evaluations in that it can
            # be used to compare two separate GifXML-files. One of these is the gold file,
            # against which the other is evaluated by heuristically matching triggers and
            # edges. Note that this evaluation will differ somewhat from the previous ones,
            # which evaluate on the level of examples.
            EvaluateInteractionXML.run(Ev, xml, TEST_FILE, PARSE, TOK)
            # Convert to ST-format
            STFormat.ConvertXML.toSTFormat(xml, "flat-"+str(boost)+"-geniaformat", getA2FileTag(options.task, subTask))
            
            if options.task in ["OLD", "GE"]:
                if options.unmerging:
                    GOLD_TEST_FILE = TEST_FILE.replace("-nodup", "")
                    UnmergingExampleBuilder.run("flat-"+str(boost)+".xml", GOLD_TEST_FILE, "unmerging-grid-examples", PARSE, TOK, UNMERGING_FEATURE_PARAMS, UNMERGING_IDS)
                    Cls.test(UNMERGING_TEST_EXAMPLE_FILE, bestUnmergingModel, "unmerging-grid-classifications")
                    unmergedXML = BioTextExampleWriter.write("unmerging-grid-examples", "unmerging-grid-classifications", "flat-"+str(boost)+".xml", "unmerged-"+str(boost)+".xml", UNMERGING_IDS+".class_names", PARSE, TOK)
                    STFormat.ConvertXML.toSTFormat(unmergedXML, "unmerged-"+str(boost)+"-geniaformat", getA2FileTag(options.task, subTask))
                    results = evaluateSharedTask("unmerged-"+str(boost)+"-geniaformat", subTask)
                    if bestResults == None or bestResults[1]["approximate"]["ALL-TOTAL"]["fscore"] < results["approximate"]["ALL-TOTAL"]["fscore"]:
                        bestResults = (boost, results)
                if options.task in ["OLD", "GE"]: # rule-based unmerging
                    print >> sys.stderr, "Rule based unmerging"
                    # Post-processing
                    unmergedXML = unflatten(xml, PARSE, TOK)
                    # Output will be stored to the geniaformat-subdirectory, where will also be a
                    # tar.gz-file which can be sent to the Shared Task evaluation server.
                    gifxmlToGenia(unmergedXML, "geniaformat", subTask)
                    # Evaluation of the Shared Task format
                    results = evaluateSharedTask("geniaformat", subTask)
                    #if bestResults == None or bestResults[1]["approximate"]["ALL-TOTAL"]["fscore"] < results["approximate"]["ALL-TOTAL"]["fscore"]:
                    #    bestResults = (boost, results)
        else:
            print >> sys.stderr, "No predicted edges"
        count += 1
    print >> sys.stderr, "Booster search complete"
    print >> sys.stderr, "Tested", count, "out of", count, "combinations"
    if options.task in ["OLD", "GE"]:
        print >> sys.stderr, "Best booster parameter:", bestResults[0]
        print >> sys.stderr, "Best result:", bestResults[1]
    
