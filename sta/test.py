#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Project      : Project
# @Author       : 
# @File         : test.py
# @Description  :
import argparse
import tensorflow.compat.v1 as tf
from SASRec import SASRec
import gc
from util import *


def str2bool(v):
    if isinstance(v, bool):
        return v
    if v.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif v.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise argparse.ArgumentTypeError('Boolean value expected.')


def get_periods(args, logs):
    """
    This function returns list of periods for joint learning or continue learning
    :return: [0] for joint learning, [1, 2, ..., period_num] for continue learning
    """
    # if continue learning: periods = [1, 2, ..., period_num]
    datafiles = os.listdir(os.path.join('..', '..', 'data', args.dataset))
    period_num = int(len(list(filter(lambda file: file.endswith(".txt"), datafiles))) / 3 - 1)
    # period_num = int(len(list(filter(lambda file: file.endswith(".txt"), datafiles))))
    logs.write('\nContinue Learning: Number of periods is %d.\n' % period_num)
    periods = range(1, period_num + 1)
    return periods


if __name__ == '__main__':

    gc.enable()
    tf.disable_v2_behavior()
    tf.logging.set_verbosity(tf.logging.ERROR)
    os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"


    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', default='DIGINETICA', type=str)
    parser.add_argument('--save_dir', default='Exemplar10K', type=str) #ContinueLearning
    parser.add_argument('--desc', default='cumulative test', type=str)

    parser.add_argument('--remove_item', default=True, type=str2bool)

    # batch size and device
    # parser.add_argument('--batch_size', default=256, type=int)
    parser.add_argument('--test_batch', default=32, type=int)
    parser.add_argument('--device_num', default=0, type=int)
    # hyper-parameters grid search
    parser.add_argument('--lr', default=0.0005, type=float)
    parser.add_argument('--num_blocks', default=2, type=int)
    parser.add_argument('--num_heads', default=1, type=int)
    # hyper-parameter fixed
    parser.add_argument('--hidden_units', default=150, type=int)
    parser.add_argument('--maxlen', default=50, type=int)
    parser.add_argument('--dropout_rate', default=0.5, type=float)
    parser.add_argument('--l2_emb', default=0.0, type=float)
    parser.add_argument('--random_seed', default=555, type=int)
    args = parser.parse_args()

    # set path
    if not os.path.isdir(os.path.join('results', args.dataset + '_' + args.save_dir)):
        os.makedirs(os.path.join('results', args.dataset + '_' + args.save_dir))
    os.chdir(os.path.join('results', args.dataset + '_' + args.save_dir))
    # record logs
    logs = open('Test.txt', mode='a')
    logs.write('Data set: %s Save dir:%s Description: %s' % (args.dataset, args.save_dir, args.desc))

    # set configurations
    config = tf.ConfigProto()
    config.gpu_options.allow_growth = True
    config.allow_soft_placement = True
    # build model
    item_num = 43023 if args.dataset == 'DIGINETICA' or args.dataset == 'DIGINETICA_week' else 37486
    with tf.device('/gpu:%d' % args.device_num):
        model = SASRec(item_num, args)

    # Loop each period for continue learning #
    periods = get_periods(args, logs)
    data_loader = DataLoader(args, logs)
    test_sess = dict()
    for period in periods:
        print('Period %d:' % period)
        logs.write('Period %d:\n' % period)

        # Load data
        data_loader.train_loader(period, 'train')
        test_sess[period] = data_loader.evaluate_loader(period, 'test')
        # data_loader.train_loader(period, 'week')
        # test_sess[period] = data_loader.evaluate_loader(period+1, 'week')
        max_item = data_loader.max_item()

        # Start of the main algorithm
        # if period != periods[-2]:
        #     continue
        with tf.Session(config=config) as sess:

            saver = tf.train.Saver(max_to_keep=1)

            epoch = 200
            while not os.path.isfile('model/period%d/epoch=%d.ckpt.index' %(period, epoch)):
                epoch -= 1
                if epoch == 0:
                    raise ValueError('Wrong model direction or no model')

            # test performance
            saver.restore(sess, 'model/period%d/epoch=%d.ckpt' % (period, epoch))
            for p in sorted(test_sess.keys()):
                print('Period %d performance:' % p)
                test_evaluator = Evaluator(args, test_sess[p], max_item, 'test', model, sess, logs)
                test_evaluator.evaluate(epoch)
        print('')

    logs.write('Done\n\n')
    logs.close()
    print('Done')





