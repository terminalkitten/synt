# -*- coding: utf-8 -*-
from nltk import NaiveBayesClassifier, FreqDist, ELEProbDist
from utils.db import RedisManager, get_samples
from collections import defaultdict

def train(db, samples=200000, classifier='naivebayes', best_features=10000, processes=8, purge=False):
    """
    Train with samples from sqlite database and stores the resulting classifier in Redis.
  
    Keyword arguments:
    samples         -- the amount of samples to train on
    classifier      -- the classifier to use 
                       NOTE: currently only naivebayes is supported
    best_features   -- amount of highly informative features to store
    processes       -- will be used for counting features in parallel 
    """
   
    m = RedisManager(purge=purge)
    m.r.set('training_sample_count', samples)

    if classifier in m.r.keys():
        print("Classifier exists in Redis. Purge to re-train.")
        return

    train_samples = get_samples(db, samples)

    m.store_feature_counts(train_samples, processes=processes)
    m.store_freqdists()
    m.store_feature_scores()
   
    best_words = None
    if best_features:
        m.store_best_features(best_features)
        best_words = m.get_best_features()

    label_freqdist = FreqDist()
    feature_freqdist = defaultdict(FreqDist)

    neg_processed, pos_processed = m.r.get('negative_processed'), m.r.get('positive_processed')
    label_freqdist.inc('negative', int(neg_processed))
    label_freqdist.inc('positive', int(pos_processed))

    conditional_fd = m.pickle_load('label_fd')
    
    labels = conditional_fd.conditions()

    for label in labels:
        samples = label_freqdist[label]
        for fname in best_words:
            trues = conditional_fd[label][fname] #is the count it happened
            falses = samples - trues
            feature_freqdist[label, fname].inc(True, trues)
            feature_freqdist[label, fname].inc(False,falses)

    # Create the P(label) distribution
    estimator = ELEProbDist
    label_probdist = estimator(label_freqdist)
    
    # Create the P(fval|label, fname) distribution
    feature_probdist = {}
    for ((label, fname), freqdist) in feature_freqdist.items():
        probdist = estimator(freqdist, bins=2) 
        feature_probdist[label,fname] = probdist
    
    c = NaiveBayesClassifier(label_probdist, feature_probdist)
    
    #TODO: support various classifiers
    m.store_classifier(classifier, c)

if __name__ == "__main__":
    #example train
    import time

    db = 'samples.db'
    samples = 400000 
    best_features = 5000 
    processes = 8
    purge = True

    print("Beginning train on {} samples using '{}' db..".format(samples, db))
    start = time.time()
    train(
        db            = db, 
        samples       = samples,
        best_features = best_features,
        processes     = processes,
        purge         = purge,
    )

    print("Successfully trained in {} seconds.".format(time.time() - start))
