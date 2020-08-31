from __future__ import print_function
import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from copy import deepcopy
from backdoor_utils import Backdoor_Utils
from backdoor_semantic_utils import SemanticBackdoor_Utils

import utils
path_to_aggNet="./aggNet/aggNet_dim64_199.pt"

class Server():
    def __init__(self,model,dataLoader,criterion=F.nll_loss,device='cpu'):
        self.clients=[]
        self.model=model
        self.dataLoader=dataLoader
        self.device=device
        self.emptyStates=None
        self.init_stateChange()
        self.Delta=None
        self.iter=0
        self.GAR=self.FedAvg
        self.func=torch.mean
        self.isSaveChanges=False
        self.savePath='./AggData'
        self.criterion=criterion
        self.path_to_aggNet="./aggNet/net.pt"
        
    def init_stateChange(self):
        states=deepcopy(self.model.state_dict())
        for param,values in states.items():
            values*=0
        self.emptyStates=states
    
    def attach(self, c):
        self.clients.append(c)
    def distribute(self):
        for c in self.clients:
            c.setModelParameter(self.model.state_dict())
    def test(self):
        self.model.to(self.device)
        self.model.eval()
        test_loss = 0
        correct = 0
        count = 0
        with torch.no_grad():
            for data, target in self.dataLoader:
                data, target = data.to(self.device), target.to(self.device)
                output = self.model(data)
                test_loss += self.criterion(output, target, reduction='sum').item() # sum up batch loss
                pred = output.argmax(dim=1, keepdim=True) # get the index of the max log-probability
                correct += pred.eq(target.view_as(pred)).sum().item()
                count += pred.shape[0]
        test_loss /= count
        accuracy=100. * correct / count
        self.model.cpu() ## avoid occupying gpu when idle
        print('\nTest set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n'.format(
            test_loss, correct, count, accuracy))
        return test_loss,accuracy
    
    def test_backdoor(self):
        self.model.to(self.device)
        self.model.eval()
        test_loss = 0
        correct = 0
        utils=Backdoor_Utils()
        with torch.no_grad():
            for data, target in self.dataLoader:
                data, target = utils.get_poison_batch(data, target, backdoor_fraction=1, backdoor_label=utils.backdoor_label, evaluation=True)
                data, target = data.to(self.device), target.to(self.device)
                output = self.model(data)
                test_loss += self.criterion(output, target, reduction='sum').item() # sum up batch loss
                pred = output.argmax(dim=1, keepdim=True) # get the index of the max log-probability
                correct += pred.eq(target.view_as(pred)).sum().item()

        test_loss /= len(self.dataLoader.dataset)
        accuracy=100. * correct / len(self.dataLoader.dataset)
        
        self.model.cpu() ## avoid occupying gpu when idle
        print('\nTest set (Backdoored): Average loss: {:.4f}, Success rate: {}/{} ({:.0f}%)\n'.format(
            test_loss, correct, len(self.dataLoader.dataset), accuracy))
        return test_loss,accuracy
    
    def test_semanticBackdoor(self):
        self.model.to(self.device)
        self.model.eval()
        test_loss = 0
        correct = 0
        utils=SemanticBackdoor_Utils()
        with torch.no_grad():
            for data, target in self.dataLoader:
                data, target = utils.get_poison_batch(data, target, backdoor_fraction=1, backdoor_label=utils.backdoor_label, evaluation=True)
                data, target = data.to(self.device), target.to(self.device)
                output = self.model(data)
                test_loss += self.criterion(output, target, reduction='sum').item() # sum up batch loss
                pred = output.argmax(dim=1, keepdim=True) # get the index of the max log-probability
                correct += pred.eq(target.view_as(pred)).sum().item()

        test_loss /= len(self.dataLoader.dataset)
        accuracy=100. * correct / len(self.dataLoader.dataset)
        
        self.model.cpu() ## avoid occupying gpu when idle
        print('\nTest set (Semantic Backdoored): Average loss: {:.4f}, Success rate: {}/{} ({:.0f}%)\n'.format(
            test_loss, correct, len(self.dataLoader.dataset), accuracy))
        return test_loss,accuracy, data, pred
    
        
    def train(self,group):
        selectedClients=[self.clients[i] for i in group]
        for c in selectedClients:
            c.train()
            c.update()
        debug=True
        
        if self.isSaveChanges:
            self.saveChanges(selectedClients)
        
        Delta=self.GAR(selectedClients)
        for param in self.model.state_dict():
            self.model.state_dict()[param]+=Delta[param]
        self.iter+=1
#     def worker(self,c):
#         c.train()
#         c.update()
#         return c
 
        
    def set_GAR(self,gar):
        if   gar=='fedavg':
            self.GAR=self.FedAvg
        elif gar=='median':
            self.GAR=self.FedMedian
        elif gar=='deepGAR':
            self.GAR=self.deepGAR
        elif gar=='deepGARNbh':
            self.GAR=self.deepGARNbh   
        elif gar=='baseline':
            self.GAR=self.net_baseline
        elif gar=='aggNetResidual':
            self.GAR=self.net_aggNetResidual
        elif gar=='aggNetBlocks':
            self.GAR=self.net_aggNetBlocks
        elif gar=='aggNetBlocksMultiple':
            self.GAR=self.net_aggNetBlocksMultiple
        elif gar=='aggNetBlockNormalize':
            self.GAR=self.net_aggNet_Blocks_normalize
        elif gar=='gm':
            self.GAR=self.geometricMedian
        elif gar=='krum':
            self.GAR=self.krum
        elif gar=='mkrum':
            self.GAR=self.mkrum
        elif gar=='irlsSort':
            self.GAR=self.net_irlsNeuralSort
        elif gar=='attention':
            self.GAR=self.net_attention
        else:
            raise ValueError("Not a valid aggregation rule or aggregation rule not implemented")

    def FedAvg(self,clients):
        out =self.FedFuncWholeNet(clients , lambda arr: torch.mean(arr,dim=-1,keepdim=True))
        return out#self.FedFunc(clients,func=torch.mean)
    def FedMedian(self,clients):
        out =self.FedFuncWholeNet(clients , lambda arr: torch.median(arr,dim=-1,keepdim=True)[0])
        return out#self.FedFunc(clients,func=torch.mean)
    
    def load_deep_net(self):
        
        num_clients=len(self.clients)
        net=self.Net(1,num_clients)
        net.load_state_dict(torch.load(self.path_to_aggNet))
        return net
    
    def load_deep_net_nbh(self):
        from aggNet import Net
        num_clients=len(self.clients)
        self.vector_dimension=1
        net=Net(self.vector_dimension,num_clients)
        net.load_state_dict(torch.load(self.path_to_aggNet))
        return net
    
    def deepGAR(self,clients):

        net=self.load_deep_net().cuda()
        def func(arr):
#             arr=torch.sort(arr)[0]
            with torch.no_grad():
                out=net(arr.cuda())[2].squeeze()
            return out
        return self.FedFuncPerLayer(clients,func=func)
    def deepGARWeighted(self,clients):

        net=self.load_deep_net().cuda()
        def func(arr):
#             arr=torch.sort(arr)[0]
            with torch.no_grad():
                out=net(arr.cuda())[1]
#                 d=out.size(0)
#                 a=(torch.std(out,1)@out)
#                 a=a/torch.sum(a)
#                 out=a.repeat(d,1)
            return out
        return self.FedFuncPerLayer(clients,func=func)
    
    def deepGARNbh(self,clients):

        net=self.load_deep_net_nbh().cuda()
        def func(arr):
#             arr=torch.sort(arr)[0]
            with torch.no_grad():
                out=net(arr.cuda())[2][:,0].squeeze()
            return out
        return self.FedFuncNbhPerLayer(clients,func=func,vd=self.vector_dimension)
    def net_baseline(self,clients):
        from baseline import Net
        self.Net=Net
        self.path_to_aggNet='./aggNet/baseline_dim1_199.pt'
        out=self.deepGAR(clients)
        return out
    def net_aggNetResidual(self,clients):
        from aggNet import Net
        self.Net=Net
        self.path_to_aggNet='./aggNet/aggNetRes_dim1_199.pt'
        out=self.deepGAR(clients)
        return out
    def net_aggNetBlocks(self,clients):
        from aggNet_Blocks import Net
        self.Net=Net
#         self.path_to_aggNet='./aggNet/aggNetBlock_dim1_199.pt'
        self.path_to_aggNet='./aggNet/aggNetBlock_cifar_dirichlet_dim1_20.pt'        
        out=self.deepGAR(clients)
        return out    
    def net_aggNetBlocksMultiple(self,clients):
        from agg_Blocks_Multiple import Net
        self.Net=Net
        self.path_to_aggNet='./aggNet/aggNetBlockMultiple_dim1_199.pt'
        out=self.deepGAR(clients)
        return out    
    
    def net_aggNet_Blocks_normalize(self,clients):
        from aggNet_Blocks_normalize import Net
        self.Net=Net
        self.path_to_aggNet='./aggNet/aggNetBlockNormalize_dim1_79.pt'
        out=self.deepGAR(clients)
        return out    
    def net_irlsNeuralSort(self,clients):
        from nnsort import Net
        self.Net=Net
        self.path_to_aggNet='./aggNet/GeometricMedian_dim1_132.pt'
        out=self.deepGAR(clients)
        return out
    def geometricMedian(self,clients):
        from geometricMedian import Net
        self.Net=Net
        out=self.FedFuncWholeNet(clients , lambda arr: Net().cuda()(arr.cuda()))
        return out   
    def krum(self,clients):
        from multiKrum import Net
        self.Net=Net
        out=self.FedFuncWholeNet(clients , lambda arr: Net('krum').cuda()(arr.cuda()))
        return out   
    def mkrum(self,clients):
        from multiKrum import Net
        self.Net=Net
        out=self.FedFuncWholeNet(clients , lambda arr: Net('mkrum').cuda()(arr.cuda()))
        return out   
    
    def net_attention(self,clients):
        from aggregator.attention import Net
        out=self.FedFuncWholeStateDict(clients , Net().main)
        return out   
    
    def FedFunc(self,clients,func=torch.mean):
        '''
        apply func to each paramters across clients
        '''
        Delta=deepcopy(self.emptyStates)
        deltas=[c.getDelta() for c in clients]

        for param in Delta:
            if not "FloatTensor" in Delta[param].type():
                print(f'Skip aggregating non-float parameters:{param}')
                Delta[param]=deltas[0][param]
                continue
            ##stacking the weight in the innerest dimension
            param_stack=torch.stack([delta[param] for delta in deltas],-1)
            shaped=param_stack.view(-1,len(clients))
#             print(shaped.type())
            ##applying `func` to every array (of size `num_clients`) in the innerest dimension
            buffer=torch.stack(list(map(func,[shaped[i] for i in range(shaped.size(0))]))).reshape(Delta[param].shape)
            Delta[param]=buffer
        return Delta
    
    def saveChanges(self, clients):
        
        Delta=deepcopy(self.emptyStates)
        deltas=[c.getDelta() for c in clients]

        for param in Delta:
            if not "FloatTensor" in Delta[param].type():
                continue
            ##stacking the weight in the innerest dimension
            param_stack=torch.stack([delta[param] for delta in deltas],-1)
            shaped=param_stack.view(-1,len(clients))
            Delta[param]=shaped
            
        saveAsPCA=True
        if saveAsPCA:
            import convert_pca
            proj_vec=convert_pca._convertWithPCA(Delta)
            savepath=f'{self.savePath}/pca_{self.GAR.__name__}_{self.iter}.pt'
            torch.save(proj_vec,savepath)
            return
        savepath=f'{self.savePath}/{self.GAR.__name__}_{self.iter}.pt'
        
        torch.save(Delta,savepath)
        print(f'Weight delta has been saved to {savepath}')
        
        
        
    def FedFuncNbhPerLayer(self,clients,func=torch.mean,vd=1):
        '''
        apply func to each layer across clients
        for each entry in the layer, sample (vd-1) other entries in the layer with that entry,
        feed it to the GAR
        '''
        Delta=deepcopy(self.emptyStates)
        deltas=[c.getDelta() for c in clients]
        
        def getNbh(t1,vd):
            '''
            -in
            t1: tensor with shape d1 x 1 x num clients
            vd: the dimension of the vector to be fed to deep GAR, equals to the number of nbh  to be sampled
            -out
            entriesWithNbh: tensor with shape d1 x vd x num clients, with entriesWithNbh[:,0,:] being the original entry 
            '''
            d1=t1.size(0)
            num_clients=t1.size(2)
            randperms=[torch.tensor(range(d1))]+[torch.randperm(t1.size(0)) for i in range(vd-1)]
            randperms_index=torch.stack(randperms,dim=1)
            entriesWithNbh=t1[randperms_index].view(-1,vd,num_clients)
            return entriesWithNbh
            
        for param in Delta:
            if not "FloatTensor" in Delta[param].type():
                print(f'Skip aggregating non-float parameters:{param}')
                Delta[param]=deltas[0][param]
                continue
            ##stacking the weight in the innerest dimension
            ## size of layer x1x number of clients
            param_stack=torch.stack([delta[param] for delta in deltas],-1) # d1 x d2 x d3 x... xnum clients
            shaped=param_stack.view(-1,1,len(clients)) #d1*d2*d3*... x 1 x num clients
            dset=torch.utils.data.TensorDataset(shaped)
            dloader=torch.utils.data.DataLoader(dset,batch_size=8192) #num entry in layer x vd x num clients
            result=[]
            for data in dloader:
#                 print(data[0].shape)
                data_withNbh=getNbh(data[0],vd)
#                 print(data_withNbh.shape)
                result.append(func(data_withNbh))
            #result: sequence of b x 1 tensors, b may differ
            result_tensor=torch.cat(result)
            buffer=result_tensor.reshape(Delta[param].shape)
            ##applying `func` to the [n by params] tensor in the innerest dimension
#             buffer=func(shaped).reshape(Delta[param].shape)
            Delta[param]=buffer
        return Delta
        
    def FedFuncPerLayer(self,clients,func=torch.mean):
        '''
        apply func to each layer across clients
        '''
        Delta=deepcopy(self.emptyStates)
        deltas=[c.getDelta() for c in clients]

        for param in Delta:
            if not "FloatTensor" in Delta[param].type():
                print(f'Skip aggregating non-float parameters:{param}')
                Delta[param]=deltas[0][param]
                continue
            ##stacking the weight in the innerest dimension
            ## size of layer x1x number of clients
            param_stack=torch.stack([delta[param].cpu() for delta in deltas],-1) # d1 x d2 x d3 x... xnum clients
            shaped=param_stack.view(-1,1,len(clients)) #d1*d2*d3*... x 1 x num clients
            dset=torch.utils.data.TensorDataset(shaped)
            dloader=torch.utils.data.DataLoader(dset,batch_size=8192)
            result=[]
            for data in dloader:
                result.append(func(data[0]))
            result_tensor=torch.cat(result)
            buffer=result_tensor.reshape(Delta[param].shape)
            ##applying `func` to the [n by params] tensor in the innerest dimension
#             buffer=func(shaped).reshape(Delta[param].shape)
            Delta[param]=buffer
        return Delta
    def FedFuncPerLayer_1_batch(self,clients,func=torch.mean):
        '''
        apply func to each layer across clients
        '''
        Delta=deepcopy(self.emptyStates)
        deltas=[c.getDelta() for c in clients]

        for param in Delta:
            if not "FloatTensor" in Delta[param].type():
                print(f'Skip aggregating non-float parameters:{param}')
                Delta[param]=deltas[0][param]
                continue
            ##stacking the weight in the innerest dimension
            ## size of layer x1x number of clients
            param_stack=torch.stack([delta[param].cpu() for delta in deltas],-1) # d1 x d2 x d3 x... xnum clients
            shaped=param_stack.view(1,-1,len(clients)) #d1*d2*d3*... x 1 x num clients
            result_tensor=func(shaped)
            buffer=result_tensor.reshape(Delta[param].shape)
            ##applying `func` to the [n by params] tensor in the innerest dimension
#             buffer=func(shaped).reshape(Delta[param].shape)
            Delta[param]=buffer
        return Delta        
    def FedFuncWholeNet(self,clients,func):
        Delta=deepcopy(self.emptyStates)
        deltas=[c.getDelta() for c in clients]

        vecs=[utils.net2vec(delta) for delta in deltas]
        result=func(torch.stack(vecs,1).unsqueeze(0)) #input as 1 by d by n
        result=result.view(-1)
        param_float=utils.getFloatSubModules(Delta)        
        
        for param in Delta:
            if param not in param_float:
                print(f'Skip aggregating non-float parameters:{param}')
                Delta[param]=deltas[0][param]
                
        utils.vec2net(result,Delta)
        return Delta
    
    def FedFuncWholeStateDict(self,clients,func):
        Delta=deepcopy(self.emptyStates)
        deltas=[c.getDelta() for c in clients]
        
        resultDelta=func(deltas)

        Delta.update(resultDelta)        
        return Delta