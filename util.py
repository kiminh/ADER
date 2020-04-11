#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Project      : Project
# @Author       : Xiaoyu LIN
# @File         : util.py
# @Description  :
import random
import os
import pickle
import numpy as np
from tqdm import tqdm
from collections import defaultdict
from matplotlib import pyplot as plt


class DataLoader:
    """
    DataLoader object to load train, valid and test data from dataset.
    """

    def __init__(self, args, logs):
        """
        :param args: args
        :param logs: logs
        """
        self.item_set = set()
        self.path = os.path.join('..', '..', 'data', args.dataset)
        self.is_remove_item = args.remove_item
        self.logs = logs
        self.item_counter = defaultdict(lambda: 0)

    def train_loader(self, period):
        """
        This method return train data of specific period
        :param period: current period
        :return: train data of current period
        """
        Sessions = defaultdict(list)
        with open(self.path + '/train_%d.txt' % period, 'r') as f:
            for line in f:
                sessId, itemId = line.rstrip().split(' ')
                sessId = int(sessId)
                itemId = int(itemId)
                self.item_set.add(itemId)
                Sessions[sessId].append(itemId)
                self.item_counter[itemId] += 1
        sessions = list(Sessions.values())
        if period > 1:
            sessions.extend(self.load_previous_evaluate_data(period))
        info = 'Train set information: total number of action: %d.' \
               % sum(list(map(lambda session: len(session), sessions)))
        self.logs.write(info + '\n')
        print(info)
        return sessions

    def load_previous_evaluate_data(self, period):
        """
        This method return valid and test data from previous period to be extended behind current train data
        :param period: current period
        :return valid and test data from previous period
        """
        period = period - 1
        Sessions = defaultdict(list)
        for name in ['valid', 'test']:
            with open(self.path + '/%s_%d.txt' % (name, period), 'r') as f:
                for line in f:
                    sessId, itemId = line.rstrip().split(' ')
                    sessId = int(sessId)
                    itemId = int(itemId)
                    self.item_set.add(itemId)
                    self.item_counter[itemId] += 1
                    Sessions[sessId].append(itemId)
        return list(Sessions.values())

    # def get_cumulative(self):
    #     """
    #     This method return cumulative numbers among items according to their frequency
    #     :return: list of cumulative numbers with length of maximum item
    #     """
    #     max_item = self.max_item()
    #     item_count = np.zeros(max_item)
    #     for item in self.item_counter.keys():
    #         item_count[item - 1] = self.item_counter[item]
    #     cumulative = np.zeros_like(item_count, dtype=np.uint32)
    #
    #     ns_exponent = 0.75
    #     train_words_pow = np.sum(item_count ** ns_exponent)
    #     cum = 0.0
    #     for idx in range(max_item):
    #         cum += item_count[idx] ** ns_exponent
    #         cumulative[idx] = round(cum / train_words_pow * 2 ** 32 - 1)
    #     return cumulative

    def get_item_counter(self):
        """
        This method return numbers of
        :return: list of cumulative numbers with length of maximum item
        """
        max_item = self.max_item()
        item_count = np.zeros(max_item)
        for item in self.item_counter.keys():
            item_count[item - 1] = self.item_counter[item]

        return item_count

    def evaluate_loader(self, period, mode):
        """
        This method load and return test or valid data according to mode of specific period
        :param period: current period
        :param mode: 'test' or 'valid'
        :return: test or valid data according to mode
        """
        Sessions = defaultdict(list)
        removed_num = 0
        total_num = 0
        self.item_counter = defaultdict(lambda: 0)
        with open(self.path + '/%s_%d.txt' % (mode, period), 'r') as f:
            for line in f:
                total_num += 1
                sessId, itemId = line.rstrip().split(' ')
                sessId = int(sessId)
                itemId = int(itemId)
                # remove new items in test or validation set that not appear in train set
                if self.is_remove_item and (itemId not in self.item_set):
                    removed_num += 1
                    continue
                self.item_set.add(itemId)
                self.item_counter[itemId] += 1
                Sessions[sessId].append(itemId)

        if self.is_remove_item:
            delete_keys = []
            for sessId in Sessions:
                if len(Sessions[sessId]) == 1:
                    removed_num += 1
                    self.item_counter[Sessions[sessId][0]] -= 1
                    delete_keys.append(sessId)
            for delete_key in delete_keys:
                del Sessions[delete_key]

        if mode == 'test':
            info = 'Test'
        else:
            info = 'Validation'
        info = '%s set information: original total number of action: %d, removed number of action: %d.' \
               % (info, total_num, removed_num)
        self.logs.write(info + '\n')
        print(info)
        sessions = list(Sessions.values())
        return sessions

    def max_item(self):
        """
        This method returns the maximum item in item set.
        """
        if len(self.item_set) != max(self.item_set):
            print('Item index error!')
            self.logs.write('Item index error!')
        return max(self.item_set)


class Sampler:
    """
    This object samples data and generates positive labels for train, valid and test, as well as negative sample for
    train.
    """

    def __init__(self, args, data, is_train, max_item=None, cumulative=None):
        """
        :param args: args
        :param data: original data for sampling
        :param is_train: boolean: train or evaluation (valid/test) sampler, for train, it also return negative sample
        :param max_item: maximum item in train dataset, to generate negative sample randomly
        :param cumulative: cumulative list according to item frequency, to generate negative sample by frequency
        """
        self.data = data
        self.max_item = max_item
        self.maxlen = args.maxlen
        self.is_train = is_train
        self.cumulative = cumulative
        if is_train:
            self.batch_size = args.batch_size
        else:
            self.batch_size = args.test_batch
        SEED = random.randint(0, 2e9)
        random.seed(SEED)

    def label_generator(self, session):
        """
        This method return input sequence as well as positive and negative sample
        :param session: a item sequence
        :return: train: input sequence, positive sample (label sequence), negative sample
                 valid/test: input sequence, positive sample (label sequence)
        """
        seq = np.zeros([self.maxlen], dtype=np.int32)
        pos = np.zeros([self.maxlen], dtype=np.int32)
        nxt = session[-1]
        idx = self.maxlen - 1
        if self.is_train:
            neg = np.zeros([self.maxlen], dtype=np.int32)

        for itemId in reversed(session[:-1]):
            seq[idx] = itemId
            pos[idx] = nxt
            if nxt != 0 and self.is_train:
                neg[idx] = self.negative_generator(session)
            nxt = itemId
            idx -= 1
            if idx == -1:
                break

        if self.is_train:
            return seq, pos, neg
        else:
            return seq, pos

    def negative_generator(self, session):
        """
        This method generate negative sample. If cumulative is given, it generate by item frequency
        :param session: the generated negative sample should not in the original session
        """
        if self.cumulative is None:
            neg = random.randint(1, self.max_item)
            while neg in session:
                neg = random.randint(1, self.max_item)
        else:
            neg = self.cumulative.searchsorted(np.random.randint(self.cumulative[-1])) + 1
            while neg in session:
                neg = self.cumulative.searchsorted(np.random.randint(self.cumulative[-1])) + 1
        return neg

    def exempler_sampler(self):
        """
        This method returns a batch of sample: (seq, pos (,neg))
        """
        one_batch = []
        for i in range(self.batch_size):
            session = random.choice(self.data)
            while len(session) <= 1:
                session = random.choice(self.data)
            one_batch.append(self.label_generator(session))
        return zip(*one_batch)

    def narm_sampler(self):
        """
        This method returns a batch of sample: (seq, pos (,neg))
        """
        one_batch = []
        for i in range(self.batch_size):
            session = random.choice(self.data)
            while len(session) <= 1:
                session = random.choice(self.data)
            length = len(session)
            one_batch.append(self.label_generator(session))
            if length > 2:
                for t in range(1, length - 1):
                    one_batch.append(self.label_generator(session[:-t]))
        return zip(*one_batch)

    # def bi_sampler(self):
    #     """
    #     This method returns a batch of sample: (seq, pos (,neg))
    #     """
    #     one_batch = []
    #     for i in range(self.batch_size):
    #         session = random.choice(self.data)
    #         while len(session) <= 1:
    #             session = random.choice(self.data)
    #         length = len(session)
    #         one_batch.append(self.label_generator(session))
    #         if length > 2:
    #             for t in range(1, length - 1):
    #                 one_batch.append(self.label_generator(session[:-t]))
    #         rev_session = list(reversed(session))
    #         one_batch.append(self.label_generator(rev_session))
    #         if length > 2:
    #             for t in range(1, length - 1):
    #                 one_batch.append(self.label_generator(rev_session[:-t]))
    #     return zip(*one_batch)

    # def evaluate_negative_sampler(self):
    #     """
    #     This method returns a batch of sample: (seq, pos) this method is specific designed for negative sample
    #     evaluation when item only occur once in pos set.
    #     """
    #     one_batch = []
    #     ground_truth = []
    #     for i in range(self.batch_size):
    #         session = random.choice(self.data)
    #         while (len(session) <= 1) or session[-1] in ground_truth:
    #             session = random.choice(self.data)
    #         ground_truth.append(session[-1])
    #         one_batch.append(self.label_generator(session))
    #     return zip(*one_batch)


class Evaluator:
    """
    This object evaluates performance on valid or test data.
    """

    def __init__(self, args, data, max_item, model, mode, sess, logs):
        """
        :param args: args
        :param data: data to evaluate, valid data or test data
        :param max_item: maximum item at current period
        :param model: model
        :param mode: 'valid' or 'test'
        :param sess: tf session
        :param logs: logs
        """
        self.data = data
        self.max_item = max_item
        self.mode = mode
        self.sess = sess
        self.model = model
        self.logs = logs
        self.args = args

        self.ranks = []
        self.recall_20 = 0
        self.batch_num = int(len(data) / args.test_batch)
        self.desc = 'Validating epoch ' if mode == 'valid' else 'Testing epoch '

    def last_item(self, epoch):
        """
        This method only evaluate performance of predicted last item among all existing item.
        :param epoch: current epoch
        """
        self.ranks = []
        sampler = Sampler(args=self.args, data=self.data, max_item=self.max_item, is_train=False)
        for _ in tqdm(range(self.batch_num), total=self.batch_num, ncols=70, leave=False, unit='b',
                      desc=self.desc + str(epoch)):
            seq, pos = sampler.narm_sampler()
            predictions = self.model.predict(self.sess, seq, list(range(1, self.max_item + 1)))
            ground_truth = [sess[-1] for sess in pos]
            rank = [pred[index - 1] for pred, index in zip(predictions, ground_truth)]
            self.ranks.extend(rank)
        self.display(epoch)

    # def full_item(self, epoch):
    #     """
    #     This method evaluate performance of all predicted item among all existing item.
    #     :param epoch: current epoch
    #     """
    #     self.ranks = []
    #     sampler = Sampler(args=self.args, data=self.data, max_item=self.max_item, is_train=False)
    #     for _ in tqdm(range(self.batch_num), total=self.batch_num, ncols=70, leave=False, unit='b',
    #                   desc=self.desc + str(epoch)):
    #         seq, pos = sampler.sampler()
    #
    #         predictions = self.model.predict_all(self.sess, seq, list(range(1, self.max_item + 1)))
    #         ground_truth = np.array(pos).flatten()
    #
    #         predictions = predictions[np.where(ground_truth != 0)]
    #         ground_truth = ground_truth[np.where(ground_truth != 0)]
    #
    #         rank = [pred[index - 1] for pred, index in zip(predictions, ground_truth)]
    #         self.ranks.extend(rank)
    #     self.display(epoch)

    # def neg_sample_last_item(self, epoch, neg_sample_num):
    #     """
    #     This method only evaluate performance of predicted last item among a fix number of negative samples.
    #     :param epoch: current epoch
    #     :param neg_sample_num: number of negative samoples
    #     """
    #     self.ranks = []
    #     args = self.args
    #     neg_sample_num += 1
    #     args.test_batch = neg_sample_num
    #     batch_num = int(len(self.data) / neg_sample_num)
    #     sampler = Sampler(args=args, data=self.data, max_item=self.max_item, is_train=False)
    #     for _ in tqdm(range(batch_num), total=batch_num, ncols=70, leave=False, unit='b',
    #                   desc=self.desc + str(epoch)):
    #         seq, pos = sampler.evaluate_negative_sampler()
    #
    #         ground_truth = [item[-1] for item in pos]
    #         predictions = self.model.predict(self.sess, seq, ground_truth)
    #         rank = [pred[ground_truth.index(label)] for label, pred in zip(ground_truth, predictions)]
    #         self.ranks.extend(rank)
    #     self.display(epoch)

    # def neg_sample_full_item(self, epoch, neg_sample_num):
    #     """
    #     This method evaluate performance of all predicted item among a fix number of negative samples.
    #     :param epoch: current epoch
    #     :param neg_sample_num: number of negative samoples
    #     """
    #     self.ranks = []
    #     args = self.args
    #     args.test_batch = 1
    #     sampler = Sampler(args=args, data=self.data, max_item=self.max_item, is_train=False)
    #     for _ in tqdm(range(len(self.data)), total=len(self.data), ncols=70, leave=False, unit='b',
    #                   desc=self.desc + str(epoch)):
    #         seq, pos = sampler.evaluate_negative_sampler()
    #         seq = seq[0]
    #         seq = np.expand_dims(seq, axis=0)
    #         pos = pos[0]
    #         test_item = list(set(pos.tolist()))
    #         if 0 in test_item: test_item.remove(0)
    #         while len(test_item) < (neg_sample_num + 1):
    #             neg_sample = random.randint(1, self.max_item)
    #             if neg_sample not in test_item:
    #                 test_item.append(neg_sample)
    #
    #         predictions = self.model.predict_all(self.sess, seq, test_item)
    #         ground_truth = pos.flatten()
    #
    #         predictions = predictions[np.where(ground_truth != 0)]
    #         ground_truth = ground_truth[np.where(ground_truth != 0)]
    #
    #         rank = [pred[test_item.index(label)] for pred, label in zip(predictions, ground_truth)]
    #         self.ranks.extend(rank)
    #     self.display(epoch)

    def results(self):
        """
        This method returns evaluation metrics(MRR@20, RECALL@20, MRR@10, RECALL@10)
        """
        valid_user = len(self.ranks)
        valid_ranks_20 = list(filter(lambda x: x < 20, self.ranks))
        valid_ranks_10 = list(filter(lambda x: x < 10, self.ranks))
        RECALL_20 = len(valid_ranks_20)
        MRR_20 = sum(map(lambda x: 1.0 / (x + 1), valid_ranks_20))
        RECALL_10 = len(valid_ranks_10)
        MRR_10 = sum(map(lambda x: 1.0 / (x + 1), valid_ranks_10))
        self.recall_20 = RECALL_20 / valid_user
        return MRR_20 / valid_user, RECALL_20 / valid_user, MRR_10 / valid_user, RECALL_10 / valid_user

    def display(self, epoch):
        """
        This method display and save evaluation metrics(MRR@20, RECALL@20, MRR@10, RECALL@10)
        """
        results = self.results()
        info = 'epoch:%d, %s (MRR@20: %.4f, RECALL@20: %.4f, MRR@10: %.4f, RECALL@10: %.4f)' \
               % (epoch, self.mode, results[0], results[1], results[2], results[3])
        print(info)
        self.logs.write(info + '\n')


class ExemplarGenerator:
    """
    This object select exemplars from given dataset
    """

    def __init__(self, args, max_item, m, data, mode):
        """
        :param args: args
        :param max_item: number of existing items
        :param m: number of exemplars per item
        :param data: dataset, train data or valid data
        :param mode: 'train' or 'valid'
        """
        self.sess_rep_by_item = defaultdict(list)
        self.exemplars = dict()
        self.m = m
        self.mode = mode
        self.args = args
        self.max_item = max_item

    def sort_by_last_item(self, model, sess):
        """
        This method sorts sessions by their last item.
        """
        self.sess_rep_by_item = defaultdict(list)
        sampler = Sampler(args=self.args, data=self.data, max_item=self.max_item, is_train=False)
        batch_num = int(len(self.data) / self.args.batch_size) + 1
        for _ in range(batch_num):
            seq, pos = sampler.narm_sampler()
            rep_last = sess.run(model.rep_last, {model.input_seq: seq, model.is_training: False})
            pos = np.array(pos)[:, -1]
            for session, item, rep in zip(seq, pos, rep_last):
                session = np.append(session, item)
                self.sess_rep_by_item[item].append([session, rep])

    # def sort_by_full_item(self, model, sess):
    #     """
    #     This method splits sessions into sub-sessions and sorts those sub-sessions by the next item
    #     """
    #     self.sess_rep_by_item = defaultdict(list)
    #     for _ in range(self.batch_num):
    #         seq, pos = self.sampler.sampler()
    #         rep_full = sess.run(model.rep_full, {model.input_seq: seq, model.is_training: False})
    #         for sessions, ground_truth, representative in zip(seq, pos, rep_full):
    #             for i in range(1, self.args.maxlen + 1):
    #                 if i > 1 and ground_truth[-(i - 1)] != 0 and ground_truth[-i] == 0: break
    #                 item = ground_truth[-i]
    #                 rep = representative[-i]
    #                 session = sessions[:-i]
    #                 while len(session) < self.args.maxlen:
    #                     session = np.append(session, 0)
    #                 session = np.append(session, item)
    #                 self.sess_rep_by_item[item].append([session, rep])

    def herding(self, rep, item, seq, m):
        """
        Herding algorithm for exempler selection
        :param rep: representations
        :param item: label
        :param seq: input session (item sequence)
        :param m: number of exemplar per label
        """
        # Initialize mean and selected ids
        D = rep.T / np.linalg.norm(rep.T, axis=0)
        mu = D.mean(axis=1)
        w_t = mu
        step_t = 0
        while not (len(self.exemplars[item]) == m) and step_t < 1.5 * m:
            tmp_t = np.dot(w_t, D)
            ind_max = np.argmax(tmp_t)
            w_t = w_t + mu - D[:, ind_max]
            tmp_exemplar = seq[ind_max].tolist()
            step_t += 1
            if tmp_exemplar not in self.exemplars[item]:
                self.exemplars[item].append(tmp_exemplar)

    # def herding_by_item(self):
    #     """
    #     This method selects exemplars using herding and selects equivalent number of exemplar for each label.
    #     """
    #     self.exemplars = dict()
    #     self.exemplars = {item: [] for item in self.sess_rep_by_item}
    #     for item in self.sess_rep_by_item:
    #         seq, rep = zip(*self.sess_rep_by_item[item])
    #         seq = np.array(seq)
    #         rep = np.array(rep)
    #         self.herding(rep, item, seq, self.m)

    def herding_by_frequency(self, item_count):
        """
        This method selects exemplars using herding and selects exemplars, the number of exemplars is proportional to
        item frequency.
        """
        self.exemplars = defaultdict(list)
        item_count = np.array(item_count)
        item_count = np.around(item_count * (self.m/item_count.sum()), decimals=1)
        for item in self.sess_rep_by_item:
            seq, rep = zip(*self.sess_rep_by_item[item])
            seq = np.array(seq)
            rep = np.array(rep)
            m = item_count[item-1]
            if m > 0:
                self.herding(rep, item, seq, m)

    def herding_by_period(self):
        """
        This method selects exemplars using herding algorithm among all labels.
        """
        self.exemplars = dict()
        self.exemplars = {'herding_period': []}
        full_data = []
        for item in self.sess_rep_by_item:
            full_data.extend(self.sess_rep_by_item[item])
        seq, rep = zip(*full_data)
        seq = np.array(seq)
        rep = np.array(rep)
        self.herding(rep, 'herding_period', seq, self.m)

    # def randomly_by_item(self):
    #     """
    #     This method randomly selects exemplars, and selects equivalent number of exemplar for each label.
    #     """
    #     self.exemplars = dict()
    #     self.exemplars = {item: [] for item in self.sess_rep_by_item}
    #     for item in self.sess_rep_by_item:
    #         seq, _ = zip(*self.sess_rep_by_item[item])
    #         seq = np.array(seq)
    #         seq_num = len(seq)
    #         if seq_num > self.m:
    #             selected_ids = np.random.choice(seq_num, self.m, replace=False)
    #         else:
    #             selected_ids = list(range(seq_num))
    #         self.exemplars[item] = [seq[i].tolist() for i in selected_ids]

    def randomly_by_frequency(self, item_count):
        """
        This method randomly selects exemplars, and selects equivalent number of exemplar for each label.
        """
        self.exemplars = defaultdict(list)
        item_count = np.array(item_count)
        item_count = np.around(item_count * (self.m / item_count.sum()), decimals=1)
        for item in self.sess_rep_by_item:
            seq, _ = zip(*self.sess_rep_by_item[item])
            seq = np.array(seq)
            seq_num = len(seq)
            m = item_count[item - 1]
            if m > 0:
                selected_ids = np.random.choice(seq_num, m, replace=False)
                self.exemplars[item] = [seq[i].tolist() for i in selected_ids]

    def randomly_by_period(self):
        """
        This method randomly selects exemplars among all labels.
        """
        self.exemplars = dict()
        self.exemplars = {'random_period': []}
        for _ in range(self.m):
            random_item = random.choice(list(self.sess_rep_by_item.keys()))
            seq, _ = random.choice(self.sess_rep_by_item[random_item])
            seq = seq.tolist()
            self.exemplars['random_period'].append(seq)

    def save(self, period):
        """
        This method save the generated exemplars
        """
        if not os.path.isdir('exemplar'):
            os.makedirs(os.path.join('exemplar'))
        with open('exemplar/%sExemplarPeriod=%d.pickle' % (self.mode, period), mode='wb') as file:
            pickle.dump(self.exemplars, file)

    def load(self, period):
        """
        This method load exemplar in previous period
        :param period: this period
        :return: exemplar list
        """
        exemplars = []
        with open('exemplar/%sExemplarPeriod=%d.pickle' % (self.mode, period), mode='rb') as file:
            exemplars_item = pickle.load(file)
        for item in exemplars_item.values():
            if isinstance(item, list):
                exemplars.extend([i for i in item if i])
        return exemplars


class ContinueLearningPlot:

    def __init__(self):
        # self.args = args
        self.epochs = defaultdict(list)
        self.MRR20 = defaultdict(list)
        self.RECALL20 = defaultdict(list)
        self.MRR10 = defaultdict(list)
        self.RECALL10 = defaultdict(list)

        self.MRR20_test = []
        self.RECALL20_test = []
        self.MRR10_test = []
        self.RECALL10_test = []

    def add_valid(self, period, epoch, t_valid):

        self.epochs[period].append(epoch)
        self.MRR20[period].append(t_valid[0])
        self.RECALL20[period].append(t_valid[1])
        self.MRR10[period].append(t_valid[2])
        self.RECALL10[period].append(t_valid[3])

    def best_epoch(self, period, best_epoch):

        best_epoch_idx = self.epochs[period].index(best_epoch)
        self.epochs[period] = self.epochs[period][:best_epoch_idx + 1]
        self.MRR20[period] = self.MRR20[period][:best_epoch_idx + 1]
        self.RECALL20[period] = self.RECALL20[period][:best_epoch_idx + 1]
        self.MRR10[period] = self.MRR10[period][:best_epoch_idx + 1]
        self.RECALL10[period] = self.RECALL10[period][:best_epoch_idx + 1]

    def add_test(self, t_test):
        self.MRR20_test.append(t_test[0])
        self.RECALL20_test.append(t_test[1])
        self.MRR10_test.append(t_test[2])
        self.RECALL10_test.append(t_test[3])

    def plot(self):

        x_counter = defaultdict(list)
        last_max = [0]
        for period in sorted(self.epochs.keys()):
            new_seq = [epoch + last_max[-1] for epoch in self.epochs[period]]
            x_counter[period] = new_seq
            last_max.append(new_seq[-1])

        for i, period in enumerate(sorted(self.epochs.keys())):
            if i == 0:
                plt.plot(x_counter[period], self.MRR20[period], color='r', label='MRR@20')
                plt.plot(x_counter[period], self.MRR10[period], color='g', label='MRR@10')
                plt.plot(x_counter[period], self.RECALL20[period], color='b', label='RECALL20')
                plt.plot(x_counter[period], self.RECALL10[period], color='y', label='RECALL10')
            else:
                plt.plot(x_counter[period], self.MRR20[period], color='r')
                plt.plot(x_counter[period], self.MRR10[period], color='g')
                plt.plot(x_counter[period], self.RECALL20[period], color='b')
                plt.plot(x_counter[period], self.RECALL10[period], color='y')

        test_idx = last_max[1:]
        plt.scatter(test_idx, self.MRR20_test, color='r')
        for x, y in zip(test_idx, self.MRR20_test):
            plt.text(x, y, '%.4f' % y, ha='center', va='bottom', size='x-small')
        plt.scatter(test_idx, self.MRR10_test, color='g')
        for x, y in zip(test_idx, self.MRR10_test):
            plt.text(x, y, '%.4f' % y, ha='center', va='top', size='x-small')
        plt.scatter(test_idx, self.RECALL20_test, color='b')
        for x, y in zip(test_idx, self.RECALL20_test):
            plt.text(x, y, '%.4f' % y, ha='center', va='bottom', size='x-small')
        plt.scatter(test_idx, self.RECALL10_test, color='y')
        for x, y in zip(test_idx, self.RECALL10_test):
            plt.text(x, y, '%.4f' % y, ha='center', va='bottom', size='x-small')

        x_max = last_max[-1]
        last_max = [i + 1 for i in last_max]
        last_max = last_max[:-1]
        x_label = []
        p = 1
        l = 1
        for x in range(1, x_max + 1):
            if x not in last_max:
                x_label.append(str(x - l + 1))
            else:
                l = x
                x_label.append('%d\nperiod %d' % (x - l + 1, p))
                p += 1

        plt.xticks(range(1, x_max + 1), x_label)
        plt.title('Continue learning validation results')
        plt.legend()
        plt.show()

        i = 0
        while os.path.isfile('Coutinue_Learning_results%d.pdf' % i):
            i += 1
        plt.savefig('Coutinue_Learning_results%d.pdf' % i)
        plt.close()

# class EarlyStop:
#     def __init__(self, args, saver, sess, period):
#         self.args = args
#         self.saver = saver
#         self.sess = sess
#         self.period = period
#         self.counter = 0
#         self.best_metric = 0
#         self.best_epoch = 0
#
#     def check_stop(self, epoch, metric):
#         if self.best_metric > metric:
#             self.counter += 1
#             if self.counter >= self.args.stop_iter:
#                 self.best_epoch = epoch - self.args.stop_iter * self.args.display_interval
#                 return True
#             else:
#                 return False
#         else:
#             self.counter = 0
#             self.best_metric = metric
#             self.best_epoch = epoch
#             self.saver.save(self.sess, 'model/period%d/epoch=%d.ckpt' % (self.period, epoch))
#             return False
