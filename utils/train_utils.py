import torch
from torch import nn, optim
import csv
import shutil
import numpy as np
from utils.spatial_transforms import Normalize, MultiScaleCornerCrop, MultiScaleRandomCrop
from config import Config

def set_criterion():
    """Set criterion

        Description:
        - Set criterion based on whether cuda is available or not. 
    # TODO: allow use of different criterion
    """
    criterion = nn.CrossEntropyLoss()
    return criterion.cuda()

def set_norm_method(mean, std):
    """
    Set normalization method based on mean and std

    Parameters:
    ------------
    mean : float 
        Mean value for dataset
    std : float 
        Standard deviation for dataset
    
    Returns
    ---------        
    Normalize
        Normalise class

    """
    if Config.mean_norm and not Config.std_norm:
        return Normalize([0, 0, 0], [1, 1, 1])
    elif not Config.std_norm:
        return Normalize(mean, [1, 1, 1])
    else: 
        return Normalize(mean, std)

def init_model(model):
    """Set model training devices. 
    Arguments: 
        model (class): This class must have a getModel function impletemented
    Returns:
        return pytorch model
    """
    model = model.getModel(
        num_classes=Config.n_classes
    ).cuda()
    model = nn.DataParallel(model, device_ids=None)
    params = sum(p.numel() for p in model.parameters() if p.requires_grad)
    
    return model

def set_crop_method(scales):
    """
    Set cropping method to be applied on the dataset in memory

    Args:
    -----
    scales : list 
        list of scaling ratios

    Returns:
    ---------
    Spatial Transformation

    """
    assert Config.train_crop in ['random','corner', 'center']
    crop = Config.train_crop
    if crop == 'random':
        return MultiScaleRandomCrop(scales, Config.sample_size)
    elif crop == 'corner':
        return MultiScaleCornerCrop(scales, Config.sample_size)
    elif crop == 'center':
        return MultiScaleCornerCrop(scales, Config.sample_size, crop_positions=['c'])

def set_optimizer(model):
    """
    Set optimizer algorithm:

    Args:
    ----
    model: torch.nn.Module
        Instance of nn.Module
    
    Returns: 
    --------
    torch.optim.Optimizer
    """
    assert(Config.optimizer == 'SGD' or Config.optimizer == 'Adam')

    if Config.optimizer == 'SGD':
        if Config.nesterov:
            dampening = 0
        else:
            dampening = Config.dampening

        return optim.SGD(model.parameters(), 
            lr=Config.learning_rate, 
            momentum=Config.momentum,
            dampening=dampening,
            weight_decay=Config.weight_decay,
            nesterov=Config.nesterov)

    return optim.Adam(model.parameters(), 
        lr=Config.learning_rate, 
        betas=Config.betas,
        eps=Config.eps,
        weight_decay=Config.weight_decay,
        amsgrad=Config.amsgrad)


def get_mean(norm_value=255, dataset='activitynet'):
    assert dataset in ['activitynet', 'kinetics']

    if dataset == 'activitynet':
        return [
            114.7748 / norm_value, 107.7354 / norm_value, 99.4750 / norm_value
        ]
    elif dataset == 'kinetics':
        # Kinetics (10 videos for each class)
        return [
            110.63666788 / norm_value, 103.16065604 / norm_value,
            96.29023126 / norm_value
        ]


def get_std(norm_value=255):
    # Kinetics (10 videos for each class)
    return [
        38.7568578 / norm_value, 37.88248729 / norm_value,
        40.02898126 / norm_value
    ]

class Logger(object):

    def __init__(self, path, header):
        self.log_file = open(path, 'w')
        self.logger = csv.writer(self.log_file, delimiter='\t')

        self.logger.writerow(header)
        self.header = header

    def __del(self):
        self.log_file.close()

    def log(self, values):
        write_values = []
        for col in self.header:
            assert col in values
            write_values.append(values[col])

        self.logger.writerow(write_values)
        self.log_file.flush()

class AverageMeter(object):
    """Computes and stores the average and current value"""

    def __init__(self):
        self.reset()

    def reset(self):
        self.val = 0
        self.avg = 0
        self.sum = 0
        self.count = 0

    def update(self, val, n=1):
        self.val = val
        self.sum += val * n
        self.count += n
        self.avg = self.sum / self.count

def calculate_accuracy(output, target, topk=(1,)):
    """Computes the precision@k for the specified values of k"""
    maxk = max(topk)
    batch_size = target.size(0)

    _, pred = output.topk(maxk, 1, True, True)
    pred = pred.t()
    correct = pred.eq(target.view(1, -1).expand_as(pred))

    res = []
    for k in topk:
        correct_k = correct[:k].view(-1).float().sum(0)
        res.append(correct_k.mul_(100.0 / batch_size))
    return res


def save_checkpoint(state, is_best, store_name):
    torch.save(state, '%s/%s_checkpoint.pth' % (Config.result_path, store_name))
    if is_best:
        shutil.copyfile('%s/%s_checkpoint.pth' % (Config.result_path, store_name),'%s/%s_best.pth' % (Config.result_path, Config.store_name))


def adjust_learning_rate(optimizer, epoch):
    """Sets the learning rate to the initial LR decayed by 10 every 30 epochs"""
    lr_new = Config.learning_rate * (0.1 ** (sum(epoch >= np.array(Config.lr_steps))))
    for param_group in optimizer.param_groups:
        param_group['lr'] = lr_new
        #param_group['lr'] = opt.learning_rate
