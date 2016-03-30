import numpy as np
from sklearn.linear_model import LogisticRegression
import scipy.sparse
import time
import itertools
import sys
import pickle
import inflect
import train_crf as crf
from train import load_data
import helper
import re, pdb, collections
import parse_EMA

p = inflect.engine()
# tags2int = {"TAG": 0, "shooterName":1, "killedNum":2, "woundedNum":3, "city":4}
# int2tags = ["TAG",'shooterName','killedNum','woundedNum','city']
# tags = [0,1,2,3,4]

int2tags = parse_EMA.int2tags
tags2int = parse_EMA.tags2int
tags = range(len(int2tags))

helper.load_constants()

# main loop
def main(trained_model,testing_file,viterbi,output_tags="output.tag", output_predictions="output.pred"):
    test_data, identifier = load_data(testing_file)


    ## extract features
    if not isinstance(trained_model, list):
        clf, previous_n, next_n, word_vocab,other_features = pickle.load( open( trained_model, "rb" ) )
    else:
        clf, previous_n, next_n, word_vocab,other_features = trained_model

    #print("predicting")
    tic = time.clock()
    f = open(output_tags,'w')
    #print len(test_data)
    #print len(identifier)
    for i in range(len(test_data)+len(identifier)):
        if i%2 == 1:
            y, tmp_conf = predict_tags_n(viterbi, previous_n,next_n, clf, test_data[i/2][0], word_vocab,other_features)
            f.write(" ".join([test_data[i/2][0][j]+"_"+int2tags[int(y[j])] for j in range(len(test_data[i/2][0]))]))
            f.write("\n")
        else:
            f.write(identifier[i/2])
            f.write("\n")
    #print time.clock()-tic
    f.close()
    predict_mode_batch(output_tags, output_predictions, helper.cities)
    return

# Takes in a trained model and predict all the entities
# sentence - list of words
# viterbi - bool of whether or not to use viterbi decoding
# cities - set of cities to match for backup if no city was predicted
# Returns comma separated preditions of shooterNames, killedNum, woundedNum and city with shooter names separated by '|'
def predict(trained_model, sentence, viterbi, cities):
    if type(trained_model) == str:
        clf, previous_n,next_n, word_vocab,other_features = pickle.load( open( trained_model, "rb" ) )
    else:
        #trained_model is an already initialized list of params
        clf, previous_n,next_n, word_vocab,other_features = trained_model
    sentence = sentence.replace("_"," ")
    words = re.findall(r"[\w']+|[.,!?;]", sentence)
    y, tmp_conf = predict_tags_n(viterbi, previous_n,next_n, clf, words, word_vocab,other_features)
    tags = []
    for i in range(len(y)):
        tags.append(int(y[i]))

    pred = predict_mode(words, tags, tmp_conf, cities)
    return pred

def predictWithConfidences(trained_model, sentence, viterbi, cities):
    sentence = sentence.replace("_"," ")

    words = re.findall(r"[\w']+|[.,!?;]", sentence)
    cleanedSentence = []

    i = 0
    while i < len(words):
        token = sentence[i]
        end_token_range = i
        for j in range(i+1,len(words)):
            new_token = words[j]
            if new_token == token:
                end_token_range = j
            else:
                cleanedSentence.append(words[i])
                break
        i = end_token_range + 1
    words = cleanedSentence

    if "crf" in trained_model:
        return predictCRF(trained_model, words, cities)
    if type(trained_model) == str:
        clf, previous_n,next_n, word_vocab,other_features = pickle.load( open( trained_model, "rb" ) )
    else:
        #trained_model is an already initialized list of params
        clf, previous_n,next_n, word_vocab,other_features = trained_model
    y, confidences = predict_tags_n(viterbi, previous_n,next_n, clf, words, word_vocab,other_features)
    tags = []
    for i in range(len(y)):
        tags.append(int(y[i]))

    pred, conf_scores, conf_cnts = predict_mode(words, tags, confidences, cities)

    return pred, conf_scores, conf_cnts

## Return tag, conf scores, conf counts for CRF
def predictCRF(trained_model, words, cities):
    tags, confidences = crf.predict(words, trained_model)
    pred, conf_scores, conf_cnts = predict_mode(words, tags, confidences, cities, True)
    return pred, conf_scores, conf_cnts

count_person = 0
# Make predictions using majority voting of the tag
# sentence - list of words
# tags - list of tags corresponding to sentence
# Returns comma separated preditions of shooterNames, killedNum, woundedNum and city with shooter names separated by '|'
def predict_ema_mode(sentence, tags, confidences):

    original_tags = tags

    output_entities = {}
    entity_confidences = [0,0,0]
    entity_cnts = [0,0,0]

    for tag in int2tags:
        output_entities[tag] = []

    cleanedSentence = []
    cleanedTags = []
    # print "TAGS", tags
    i = 0
    print "len sentence", len(sentence)
    while i < len(sentence):
        tag = int2tags[tags[i]]
        end_range = i
        if not tag == "TAG":
            for j in range(i+1,len(sentence)):
                new_tag = int2tags[tags[j]]
                if new_tag == tag:
                    # print "get get it", new_tag, tag, sentence[i], sentence[j]
                    # print tag
                    # print sentence[i],  sentence[j]
                    # print sentence[i:j+1]
                    # print "LOVE IT"
                    end_range = j
                else:
                    break
            # print "end_range", end_range
        cleanedSentence.append( " ".join(sentence[i:end_range+1]))
        cleanedTags.append(tags2int[tag]) 
        # if not tag == "TAG":
            # print tag, "tokens", " ".join(sentence[i:end_range+1])
            # print "---------"
        i = end_range + 1

    # print "clean sentence"
    # print cleanedSentence
    # print "cleanedTags", cleanedTags

    assert set(tags) == set(cleanedTags)
    sentence = cleanedSentence
    tags = cleanedTags
    for j in range(len(sentence)):
        ind = "" 
        ind = int2tags[tags[j]]
        output_entities[ind].append((sentence[j], confidences[j]))
    
    output_pred_line = ""

    # mode, conf = get_mode(output_entities["shooterName"])
    # output_pred_line += mode
    # entity_confidences[tags2int['shooterName']-1] += conf
    # entity_cnts[tags2int['shooterName']-1] += 1

    for tag in int2tags[1:]:
        # pdb.set_trace()
        #one idea, if ent isn't in countries, try 1perm, two perm and stop there. then run something akin to #tryCities
            
        mode, conf = get_mode(output_entities[tag])
        if mode == "":
            assert not tags2int[tag] in tags 
            assert not tags2int[tag] in original_tags 
            output_pred_line += "unknown"
            entity_confidences[tags2int[tag]-1] += 0
            entity_cnts[tags2int[tag]-1] += 1
        else:
            output_pred_line += mode
            entity_confidences[tags2int[tag]-1] += conf
            entity_cnts[tags2int[tag]-1] += 1

        if not tag == int2tags[-1]:
            output_pred_line += " ### "


    print "OUTPUT_PRED_LINE", output_pred_line

    return output_pred_line, entity_confidences, entity_cnts


def predict_mode(sentence, tags, confidences,  cities, crf=False, ema= True):
    if ema:
        return predict_ema_mode(sentence, tags, confidences)
    output_entities = {}
    entity_confidences = [0,0,0,0]
    entity_cnts = [0,0,0,0]

    for tag in int2tags:
        output_entities[tag] = []

    for j in range(len(sentence)):
        ind = "" 
        if crf:
            ind = tags[j]
        else:
            ind = int2tags[tags[j]]
        output_entities[ind].append((sentence[j], confidences[j]))
    
    output_pred_line = ""

    #for shooter (OLD)
    # for shooterName, conf in output_entities["shooterName"]:
    #     output_pred_line += shooterName.lower()
    #     output_pred_line += "|"
    #     entity_confidences[tags2int['shooterName']-1] += conf
    #     entity_cnts[tags2int['shooterName']-1] += 1
    # output_pred_line = output_pred_line[:-1]

    mode, conf = get_mode(output_entities["shooterName"])
    output_pred_line += mode
    entity_confidences[tags2int['shooterName']-1] += conf
    entity_cnts[tags2int['shooterName']-1] += 1

    for tag in int2tags:
        if tag == "city":
            output_pred_line += " ### "
            possible_city_combos = []
            # pdb.set_trace()
            for permutation in itertools.permutations(output_entities[tag],2):
                if permutation[0][0] in cities:
                    if "" in cities[permutation[0][0]]:
                        possible_city_combos.append((permutation[0][0], permutation[0][1]))
                    if permutation[1][0] in cities[permutation[0][0]]:
                        possible_city_combos.append((permutation[0][0] + " " + permutation[1][0],\
                         max(permutation[0][1], permutation[1][1]) ))
            mode, conf = get_mode(possible_city_combos)

            #try cities automatically
            if mode == "":
                possible_cities = []
                for i in range(len(sentence)):
                    word1 = sentence[i]
                    if word1 in cities:
                        if "" in cities[word1]:
                            possible_cities.append((word1, 0.))
                        if i+1 < len(sentence):
                            word2 = sentence[i+1]
                            if word2 in cities[word1]:
                                possible_cities.append((word1 + " " + word2, 0.))

                #print possible_cities
                #print get_mode(possible_cities)
                mode, conf = get_mode(possible_cities)

            output_pred_line += mode
            entity_confidences[tags2int['city']-1] += conf
            entity_cnts[tags2int['city']-1] += 1

        elif tag not in ["TAG", "shooterName"]:
            output_pred_line += " ### "

            mode, conf = get_mode(output_entities[tag])
            if mode == "":
                output_pred_line += "zero"
                entity_confidences[tags2int[tag]-1] += 0
                entity_cnts[tags2int[tag]-1] += 1
            else:
                output_pred_line += mode
                entity_confidences[tags2int[tag]-1] += conf
                entity_cnts[tags2int[tag]-1] += 1

    assert not (output_pred_line.split(" ### ")[0].strip() == "" and len(output_entities["shooterName"]) >0)

    return output_pred_line, entity_confidences, entity_cnts

# Make predictions using majority voting in batch
# output_tags - filename of tagged articles
# output_predictions - filename to write the predictions to
# Returns comma separated preditions of shooterNames, killedNum, woundedNum and city with shooter names separated by '|'
def predict_mode_batch(output_tags, output_predictions, cities):

    tagged_data, identifier = load_data(output_tags)

    f = open(output_predictions,'w')
    for i in range(len(tagged_data)+len(identifier)):
        if i%2 == 1:
            f.write(predict_mode(tagged_data[i/2][0], tagged_data[i/2][1], cities))
            f.write("\n")
        else:
            f.write(identifier[i/2])
            f.write("\n")
    return

# get mode of list l, returns "" if empty
#l consists of tuples (value, confidence)
def get_mode(l):
    counts = collections.defaultdict(lambda:0)
    Z = collections.defaultdict(lambda:0)
    curr_max = 0
    arg_max = ""
    for element, conf in l:
        try:
            normalised = p.number_to_words(int(element))
        except Exception, e:
            normalised = element.lower()


        counts[normalised] += conf
        Z[normalised] += 1

    for element in counts:
        if counts[element] > curr_max and element != "" and element != "zero":
            curr_max = counts[element]
            arg_max = element
    return arg_max, (counts[arg_max]/Z[arg_max] if Z[arg_max] > 0 else counts[arg_max])

# given a classifier and a sentence, predict the tag sequence
def predict_tags_n(viterbi, previous_n,next_n, clf, sentence, word_vocab,other_features,first_n = 10):
    num_features = len(word_vocab) + len(other_features)
    total_features = (previous_n + next_n + 1)*num_features + len(word_vocab) + previous_n * len(tags) + first_n
    dataX = np.zeros((len(sentence),total_features))
    dataY = np.zeros(len(sentence))
    dataYconfidences = [None for i in range(len(sentence))]
    other_words_lower = set([s.lower() for s in sentence[0]])
    for i in range(len(sentence)):
        word = sentence[i]
        word_lower = word.lower()
        if word_lower in word_vocab:
            dataX[i,word_vocab[word_lower]] = 1
            for j in range(previous_n):
                if i+j+1<len(sentence):
                    dataX[i+j+1,(j+1)*num_features+word_vocab[word_lower]] = 1
            for j in range(next_n):
                if i-j-1 >= 0:
                    dataX[i-j-1,(previous_n+j+1)*num_features+word_vocab[word_lower]] = 1
        for (index, feature_func) in enumerate(other_features):
            if feature_func(word):
                dataX[i,len(word_vocab)+index] = 1
                for j in range(previous_n):
                    if i + j + 1 < len(sentence):
                        dataX[i+j+1,(j+1)*num_features+len(word_vocab)+index] = 1
                for j in range(next_n):
                    if i - j - 1 >= 0:
                        dataX[i-j-1,(previous_n+j+1)*num_features+len(word_vocab)+index] = 1
        for other_word_lower in other_words_lower:
            if other_word_lower != word_lower and other_word_lower in word_vocab:
                dataX[i,(previous_n+next_n+1)*num_features + word_vocab[other_word_lower]] = 1
        if i < first_n:
            dataX[i,(previous_n + next_n + 1)*num_features + len(word_vocab) + previous_n * len(tags)+ i ] = 1
    for i in range(len(sentence)):
        for j in range(previous_n):
            if j < i:
                dataX[i,(previous_n+next_n+1)*num_features+len(word_vocab)+len(tags)*j+dataY[i-j-1]] = 1
        dataYconfidences[i] = clf.predict_proba(dataX[i,:].reshape(1, -1))
        dataY[i] = np.argmax(dataYconfidences[i])
        dataYconfidences[i] = dataYconfidences[i][0][dataY[i]]

    # pdb.set_trace()
    return dataY, dataYconfidences

if __name__ == "__main__":
    trained_model = "trained_model2.p" #sys.argv[1]
    testing_file = "../data/tagged_data/whole_text_full_city/dev.tag" #sys.argv[2]
    viterbi = False #sys.argv[4]
    main(trained_model,testing_file,viterbi)
