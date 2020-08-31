from __future__ import print_function
import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from clients import *
from backdoor_utils import Backdoor_Utils
from backdoor_semantic_utils import SemanticBackdoor_Utils
import numpy as np
import random
labels=torch.tensor([0,1,2,3,4,5,6,7,8,9])
class Attacker_LabelFlipping(Client):
    def __init__(self,cid,model,dataLoader,optimizer,criterion=F.nll_loss, device='cpu',inner_epochs=1):
        super(Attacker_LabelFlipping, self).__init__(cid,model,dataLoader,optimizer,criterion, device ,inner_epochs)
    def data_transform(self,data,target):
        labels=self.dataLoader.dataset.classes
        target_=torch.tensor(list(map(lambda x: random.choice([i for i in labels if i!=x]),target)))
        assert target.shape==target_.shape, "Inconsistent target shape"
        return data,target_    
    
class Attacker_LabelFlippingDirectional(Client):
    def __init__(self,cid,model,dataLoader,optimizer,criterion=F.nll_loss, device='cpu',inner_epochs=1):
        super(Attacker_LabelFlippingDirectional, self).__init__(cid,model,dataLoader,optimizer,criterion, device ,inner_epochs)
    def data_transform(self,data,target):
        labels=self.dataLoader.dataset.classes
        target_=torch.tensor(list(map(lambda x: labels[7] if x==labels[1] else x,target)))
        assert target.shape==target_.shape, "Inconsistent target shape"
        return data,target_

class Attacker_Backdoor(Client):
    def __init__(self,cid,model,dataLoader,optimizer,criterion=F.nll_loss, device='cpu',inner_epochs=1):
        super(Attacker_Backdoor, self).__init__(cid,model,dataLoader,optimizer,criterion, device ,inner_epochs)
        self.utils=Backdoor_Utils()

    def data_transform(self,data,target):
        data, target = self.utils.get_poison_batch(data, target, backdoor_fraction=0.5, backdoor_label = self.utils.backdoor_label)        
        return data,target

class Attacker_SemanticBackdoor(Client):
    '''
    suggested by 'How to backdoor Federated Learning' 
    https://arxiv.org/pdf/1807.00459.pdf
    
    For each batch, 20 out of 64 samples (in the original paper) are replaced with semantic backdoor, this implementation replaces on average a 30% of the batch by the semantic backdoor
    
    '''
    def __init__(self,cid,model,dataLoader,optimizer,criterion=F.nll_loss, device='cpu',inner_epochs=1):
        super(Attacker_SemanticBackdoor, self).__init__(cid,model,dataLoader,optimizer,criterion, device ,inner_epochs)
        self.utils=SemanticBackdoor_Utils()

    def data_transform(self,data,target):
        data, target = self.utils.get_poison_batch(data, target, backdoor_fraction=1.0, backdoor_label = self.utils.backdoor_label)        
        return data,target
    def testBackdoor(self):
        self.model.to(self.device)
        self.model.eval()
        test_loss = 0
        correct = 0
        utils=SemanticBackdoor_Utils()
        with torch.no_grad():
            for data, target in self.dataLoader:
                data, target = self.utils.get_poison_batch(data, target, backdoor_fraction=0.3, backdoor_label=self.utils.backdoor_label, evaluation=True)
                data, target = data.to(self.device), target.to(self.device)
                output = self.model(data)
                test_loss += self.criterion(output, target, reduction='sum').item() # sum up batch loss
                pred = output.argmax(dim=1, keepdim=True) # get the index of the max log-probability
                correct += pred.eq(target.view_as(pred)).sum().item()

        test_loss /= len(self.dataLoader.dataset)
        accuracy=100. * correct / len(self.dataLoader.dataset)
        
        self.model.cpu() ## avoid occupying gpu when idle
        print('\n(Testing at the attacker) Test set (Semantic Backdoored): Average loss: {:.4f}, Success rate: {}/{} ({:.0f}%)\n'.format(
            test_loss, correct, len(self.dataLoader.dataset), accuracy))
    def update(self):
        super().update()
        self.testBackdoor()
        
    
    
class Attacker_Omniscient(Client):
    def __init__(self,cid,model,dataLoader,optimizer,criterion=F.nll_loss, device='cpu',scale=1,inner_epochs=1):
        super(Attacker_Omniscient, self).__init__(cid,model,dataLoader,optimizer,criterion, device ,inner_epochs)
        self.scale=scale
    def update(self):
        assert self.isTrained, 'nothing to update, call train() to obtain gradients'
        newState=self.model.state_dict()
        for param in self.originalState:

            self.stateChange[param]=newState[param]-self.originalState[param]
            if not "FloatTensor" in self.originalState[param].type():
                continue
            self.stateChange[param]*=(-self.scale)
        self.isTrained=False