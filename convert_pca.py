import torch
from utils import getFloatSubModules
from sklearn.decomposition import PCA
import copy


def getPCA(component, n_components):
    pca = PCA(n_components=n_components)
    pca.fit(component.permute(1,0))
    projection = pca.transform(component.permute(1,0))
    out = torch.Tensor(projection.T)
    return out
def applyToEachSubmodule(Delta,f) -> (dict):
    '''
    apply function `f` to each submodules of `Delta`
    '''
    param_float = getFloatSubModules(Delta)

    result = dict(((k,f(Delta[k])) for k in param_float))
    out = copy.deepcopy(Delta)
    out.update(result)
    
    return out
def net2vec(net) -> (torch.Tensor):
    '''
    convert state dict to a 1 dimension Tensor
    
    Delta : torch module state dict
    
    return
    vec : torch vector with shape([d]), d is the number of Float elements in `Delta`
    '''
    param_float = getFloatSubModules(net)

    components = []
    for param in param_float:
        components.append(net[param])        
    vec = torch.cat([component for component in components ])
    return vec

def _convertWithPCA(data):
    proj = applyToEachSubmodule(data,lambda x: getPCA(x.cpu(),6))
    proj_vec = net2vec(proj)
    return proj_vec

def convertWithPCA(path_to_data):
    data = torch.load(path_to_data)
    proj_vec = _convertWithPCA(data)
    # save path defaulted to 'xxxxx/pca_FedAvg_i.pt'
    sub = path_to_data.split("/")
    sub[-1] = "pca_" + sub[-1]    
    savepath = "/".join(sub)
    
    torch.save(proj_vec,savepath)
    print(f"Done, saved to \n\t{savepath}")

if __name__ == "__main__":
    import glob
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--path_to_data_folder",         type=str, required=True,help="path to the data to be converted, e.g. \'./AggData/train_noiid_cifar/backdoor_2/\'")
    args = parser.parse_args()
    
    print("#" * 64)
    for i in vars(args):
        print(f"#{i:>20}: {str(getattr(args,i)):<20}#")
    print("#" * 64)     
    
    
    
    path_to_data_folder = args.path_to_data_folder

    
    paths_to_data = glob.glob(f"{path_to_data_folder}/FedAvg_*.pt")
    paths_to_data = sorted(paths_to_data)
    
    for (i,path_to_data) in enumerate(paths_to_data):
        print(f"{i}/{len(paths_to_data)}:{path_to_data}")
        convertWithPCA(path_to_data)