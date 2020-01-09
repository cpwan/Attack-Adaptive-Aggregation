#!/usr/bin/env python
# coding: utf-8

# In[1]:


import torchvision.datasets as dsets
from torchvision import transforms
import torch
import numpy as np
import matplotlib.pyplot as plt
torch.manual_seed(0)
num_epoch=5
batch_size=32
device='cuda'
data_root='./data'

import allocateGPU
allocateGPU.allocate_gpu()


# In[2]:


attacks=['no_attacks','omniscient','label_flipping','omniscient_aggresive']
attacker_list_labelflipping={'no_attacks':[],'omniscient':[],'label_flipping':[0],'omniscient_aggresive':[]}
attacker_list_omniscient={'no_attacks':[],'omniscient':[0],'label_flipping':[],'omniscient_aggresive':[0]}


# In[3]:


class Agg_dataset(torch.utils.data.Dataset):
    '''
        denote n be the number of clients,
        each entry of dataset is a 2-tuple of (weight delta, labels):= (1 x n tensor, 1 x n tensor)
        honest clients are labeled 1, malicious clients are labeled 0
    '''
    def __init__(self,path,attacks):
        super(Agg_dataset).__init__() 
        data=torch.load(path,map_location='cpu')
        data_tensors=torch.cat([data[param] for param in data],0)
        self.data=data_tensors
        self.label=attacks
        label=attacks/torch.sum(attacks)
        self.center=torch.sum(data_tensors*label,1).view(-1,1)
        self.num_clients=attacks.shape[0]
        self.n=10000
        dimension=1
        self.indexes=torch.randint(self.data.shape[0],(self.n,100))
        
    def __getitem__(self, index):
#         

        data_out=self.data[self.indexes[index]]
        label_out=self.label
        center_out=self.center[self.indexes[index]]
        perm=torch.randperm(self.num_clients)
#         data_sorted=torch.sort(data_out)
#         perm=data_sorted[1]
        data_out_shuffled=torch.index_select(data_out, -1, perm)

        return data_out_shuffled, [label_out[perm],center_out]
#         return data_out,[label_out,center_out]
    def __len__(self):
#         return self.data.shape[0]//100
        return self.n


# In[4]:

def get_concat_loader():
    datasets=[]
    for attack in attacks:
        label=torch.ones(10)
        for i in attacker_list_labelflipping[attack]:
            label[i]=0
        for i in attacker_list_omniscient[attack]:
            label[i]=0
        path=f'./AggData/{attack}/FedAvg_0.pt'
        dataset=Agg_dataset(path,label)
        datasets.append(dataset)
    dataset=torch.utils.data.dataset.ConcatDataset(datasets)
    validation_split = .2
    shuffle_dataset = True
    random_seed= 42

    # Creating data indices for training and validation splits:
    dataset_size = len(dataset)
    indices = list(range(dataset_size))
    split = int(np.floor(validation_split * dataset_size))
    if shuffle_dataset :
        np.random.seed(random_seed)
        np.random.shuffle(indices)
    train_indices, val_indices = indices[split:], indices[:split]

    # Creating PT data samplers and loaders:
    train_sampler = torch.utils.data.sampler.SubsetRandomSampler(train_indices)
    valid_sampler = torch.utils.data.sampler.SubsetRandomSampler(val_indices)

    train_loader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, 
                                               sampler=train_sampler)
    test_loader = torch.utils.data.DataLoader(dataset, batch_size=batch_size,
                                                    sampler=valid_sampler)
    return train_loader, test_loader


def get_loader(attack):
    label=torch.ones(10)
    for i in attacker_list_labelflipping[attack]:
        label[i]=0
    for i in attacker_list_omniscient[attack]:
        label[i]=0
    path=f'./AggData/{attack}/FedAvg_9.pt'
    dataset=Agg_dataset(path,label)
    validation_split = .2
    shuffle_dataset = True
    random_seed= 42

    # Creating data indices for training and validation splits:
    dataset_size = len(dataset)
    indices = list(range(dataset_size))
    split = int(np.floor(validation_split * dataset_size))
    if shuffle_dataset :
        np.random.seed(random_seed)
        np.random.shuffle(indices)
    train_indices, val_indices = indices[split:], indices[:split]

    # Creating PT data samplers and loaders:
    train_sampler = torch.utils.data.sampler.SubsetRandomSampler(train_indices)
    valid_sampler = torch.utils.data.sampler.SubsetRandomSampler(val_indices)

    train_loader = torch.utils.data.DataLoader(dataset, batch_size=batch_size, 
                                               sampler=train_sampler)
    test_loader = torch.utils.data.DataLoader(dataset, batch_size=batch_size,
                                                    sampler=valid_sampler)
    return train_loader, test_loader


# In[5]:


def train(net,train_loader,criterion,optimizer,device, on):
    net.to(device)
    for idx, (data,target) in enumerate(train_loader):
        data = data.to(device)
        target = target[on].to(device)
        optimizer.zero_grad()   
        output = net(data)
        loss = criterion(output[on], target)

        loss.backward()
        optimizer.step()
    
def test(net,test_loader,device,message_prefix):
    net.to(device)
    accuracy = 0
    accuracy_binary = 0
    accuracy_mean = 0
    accuracy_median = 0
    count = 0
    
    with torch.no_grad():
        for data, target in test_loader:
            data = data.to(device)
            target = target[1].to(device)
            outputs = net(data)
            accuracy+=F.l1_loss(outputs[1], target)
            accuracy_binary+=F.l1_loss(outputs[2], target)
            accuracy_mean+=F.l1_loss(data.mean(-1).unsqueeze(-1), target)
            accuracy_median+=F.l1_loss(data.median(-1)[0].unsqueeze(-1), target)
            count+=len(data)
    print('%s: \t%.4E \t %.4E \t%.4E \t%.4E' % (message_prefix,accuracy/count, accuracy_binary/count, accuracy_mean/count,accuracy_median/count ))
    return accuracy/count, accuracy_binary/count, accuracy_mean/count, accuracy_median/count


# In[7]:


# torch.mean(batch[0],-1).unsqueeze(-1).shape


# In[8]:


import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
def dot_product(A,B):
    return torch.bmm(A.view(A.shape[0],1,A.shape[1]),B.view(B.shape[0],B.shape[1],1))
class Mlp(nn.Module):
    def __init__(self,in_dim, n ,m ):
        super(Mlp, self).__init__()
        self.in_dim=in_dim
        self.n = n
        self.fc1 = nn.Linear(self.in_dim*n, m)
        self.fc2 = nn.Linear(m, m)
        self.fc3 = nn.Linear(m, self.n)

    def forward(self, input):
        x = input.view(-1, self.in_dim*self.n)
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        x = F.sigmoid(self.fc3(x))
        pred = torch.sum(x.view(-1,1,self.n)*input,dim=-1).unsqueeze(-1)/9
    
        return x,pred


# In[9]:


class CNN(nn.Module):
    def __init__(self,n,in_dim):
        super(CNN, self).__init__()
        self.in_dim=in_dim
        self.fc1 = nn.Conv1d(1, n, kernel_size=3,dilation=1, padding=1)
        self.fc2 = nn.Conv1d(n, n, kernel_size=3,dilation=2, padding=2)
        self.fc3 = nn.Conv1d(n, self.in_dim, kernel_size=3,dilation=1, padding=1)
        self.maxpool1=nn.AdaptiveMaxPool1d(1)
        

    def forward(self, input):
        x = input.view(-1, 1, self.in_dim)
        x = nn.LeakyReLU()(self.fc1(x))
        x = nn.LeakyReLU()(self.fc2(x))
        x = nn.LeakyReLU()(self.fc3(x))
        x = self.maxpool1(x)

        x=x.squeeze()
        x = F.softmax(x,dim=1)
        pred=dot_product(x,input).squeeze(-1)
        return x, pred


# In[10]:



class block(nn.Module):
    def __init__(self,in_,out_):
        super(block, self).__init__()
        self.main=torch.nn.Sequential(
                    nn.Conv2d(in_, out_, kernel_size=1),
                    torch.nn.BatchNorm2d(out_),
                    nn.ReLU(),
                    )
    def forward(self,x):
        out=self.main(x)
        return out
    
class block_no_activation(nn.Module):
    def __init__(self,in_,out_):
        super(block_no_activation, self).__init__()
        self.main=torch.nn.Sequential(
                    nn.Conv2d(in_, out_, kernel_size=1),
                    torch.nn.BatchNorm2d(out_),
                    )
    def forward(self,x):
        out=self.main(x)
        return out
    
class PointNet(nn.Module):
    def __init__(self,in_dim, n):
        '''
        in_dim:=dimension of weight vector
        n:= number of clients
        '''
        super(PointNet, self).__init__()
        self.in_dim = in_dim
        self.n = n
        self.local = torch.nn.Sequential(
                        block(self.in_dim,64),
                        block(64,64),
                        block(64,64)
                    )
        self.globa = torch.nn.Sequential(
                        block(64,128),
                        block(128,1024),
                        nn.AdaptiveMaxPool2d(1)
                    )
        self.direct_out= block(1024,10)
        self.MLP = torch.nn.Sequential(
                        block(1088,512),
                        block(512,256),
                        block(256,128),
                        nn.Dropout(p=0.7, inplace=True),
                        block_no_activation(128,1)
                      )


        

    def forward(self, input):
#         x = input.view(-1, self.n, self.in_dim)
        x=input.view(-1,self.in_dim,self.n,1)
        for module in self.local:
            x = module(x)
#             print(f'local:\t {x.shape}')
        x_local=x
        for module in self.globa:
            x = module(x)
#             print(f'global:\t {x.shape}')
        x_global=x.repeat(1,1,self.n,1)
#         print(f'tile:\t {x_global.shape}')
        x=torch.cat([x_local,x_global],dim=1)
#         print(x.shape)
        for module in self.MLP:
            x = module(x)
#             print(f'MLP:\t {x.shape}')
#         x=self.direct_out(x)
        x=x.squeeze()
#        x = F.softmax(x,dim=1)
        x = torch.sigmoid(x)
#         pred=dot_product(input,x).squeeze(-1)
        x2= F.softmax(x,dim=1)
        x3 = (x>0.5).float().cuda()
        x3 = x3/torch.sum(x3,-1).view(-1,1)
        pred = torch.sum(x2.view(-1,1,self.n)*input,dim=-1).unsqueeze(-1)
        pred_binary = torch.sum(x3.view(-1,1,self.n)*input,dim=-1).unsqueeze(-1)
        return x,pred, pred_binary




# In[11]:


from tensorboardX import SummaryWriter
def write(name,scalar):
    writer=SummaryWriter(f'./agg_logs/{name}')
    writer.add_scalar('l1 loss', scalar, 0)
    writer.close()


# In[12]:


accuracy_list={}


# In[13]:


loaders={attack:get_loader(attack) for attack in attacks}



#batch=next(iter(loaders[attacks[1]][0]))
#net_p=PointNet(100,10).cuda()
#net_p(batch[0].cuda())[0].shape


# In[33]:


mode_name=['classification']
for attack in attacks[:]:
    train_loader, test_loader=loaders[attack]
    for criterion in [torch.nn.BCELoss()]:
        mode=0
        for lr in [0.01]:

            net_ptnet=PointNet(100,10)

            for net in [net_ptnet]:
                
                training_alias=f'{attack}/{net.__class__.__name__}/{criterion.__class__.__name__}/lr_{lr}'
                if training_alias in accuracy_list:
                    continue
                
                print('Start training of %s'%training_alias)
                optimizer = optim.Adam(net.parameters(), lr=lr)
                print('L1 loss:\tmodel \tmodel (binarized) \tmean \tmedian ')
                for epoch in range(num_epoch):
                    train(net,train_loader,criterion,optimizer,device,mode)
                    score=test(net,test_loader,device,f'Epoch {epoch}')
                write(training_alias+'/weighted',score[0])
                write(training_alias+'/binary',score[1])
                accuracy_list[training_alias]=score[0].item()
    accuracy_list[f'{attack}/mean']=score[1].item()
    write(f'{attack}/mean',score[1])
    accuracy_list[f'{attack}/median']=score[2].item()
    write(f'{attack}/median',score[1])



