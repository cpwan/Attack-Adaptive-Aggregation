from __future__ import print_function
import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torchvision import datasets, transforms
from torchvision.models.vgg import vgg13_bn
from dataloader import *
import pickle

def Net():
    num_classes = 100
    model = vgg13_bn(pretrained=True)
    n = model.classifier[-1].in_features
    model.classifier[-1] = nn.Linear(n,num_classes)
    return model

def getDataset():
    dataset = datasets.CIFAR100('./data',
        train=True,
        download=True,
        transform=transforms.Compose([transforms.ToTensor(),
            transforms.Normalize((0.5,0.5,0.5), (0.5,0.5,0.5))]))
    return dataset

def basic_loader(num_clients,loader_type):
    dataset = getDataset()
    return loader_type(num_clients,dataset)

def train_dataloader(num_clients,loader_type='iid' ,store=True,path='./data/loader.pk'):
    assert loader_type in ['iid','byLabel','dirichlet'], 'Loader has to be one of the  \'iid\',\'byLabel\',\'dirichlet\''
    if loader_type == 'iid':
        loader_type = iidLoader
    elif loader_type == 'byLabel':
        loader_type = byLabelLoader
    elif loader_type == 'dirichlet':
        loader_type = dirichletLoader

        
        
    if store:
        try:
            with open(path, 'rb') as handle:
                loader = pickle.load(handle)
        except:
            print('loader not found, initialize one')
            loader = basic_loader(num_clients,loader_type)
    else:
        print('initialize a data loader')
        loader = basic_loader(num_clients,loader_type)
    if store:
        with open(path, 'wb') as handle:
            pickle.dump(loader, handle)   
    
    return loader
    

def test_dataloader(test_batch_size):
    test_loader = torch.utils.data.DataLoader(datasets.CIFAR100('./data', train=False, transform=transforms.Compose([transforms.ToTensor(),
                        transforms.Normalize((0.5,0.5,0.5), (0.5,0.5,0.5))])),
    batch_size=test_batch_size, shuffle=True)
    return test_loader
if __name__ == '__main__':
    print("#Initialize a network")
    net = Net()
    batch_size = 100
    y = net((torch.randn(batch_size,3,32,32)))
    print(f"Output shape of the network with batchsize {batch_size}:\t {y.size()}")
    
    print("\n#Initialize dataloaders")
    loader_types = ['iid','byLabel','dirichlet']
    for i in range(len(loader_types)):
        loader = train_dataloader(20,loader_types[i],store=False)
        print(f"Initialized {len(loader)} loaders (type: {loader_types[i]}), each with batch size {loader.bsz}.\
        \nThe size of dataset in each loader are:")
        print([len(loader[i].dataset) for i in range(len(loader))])
        print(f"Total number of data: {sum([len(loader[i].dataset) for i in range(len(loader))])}")
    
    print("\n#Feeding data to network")
    x = next(iter(loader[i]))[0]
    y = net(x)
    print(f"Size of input:  {x.shape} \nSize of output: {y.shape}")