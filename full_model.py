import dsc
import img2matrix
import matlab.engine
import numpy as np
import supporting_files.sda as sda
import time
from scipy.io import savemat, loadmat
from sklearn.decomposition import PCA
from sklearn.metrics import adjusted_rand_score as ari
from sklearn.metrics import normalized_mutual_info_score as nmi
from supporting_files.ji_zhang import err_rate
from supporting_files.helpers import optimize

#eng = start_matlab()

#savemat('./saved/yaleB.mat', mdict={'rawX':images_dsift, 'X':images_norm, 'Y':labels})
#images_dsift = loadmat("./saved/yaleB.mat")['rawX']
#images_norm = loadmat("./saved/yaleB.mat")['X']
#labels = loadmat("./saved/yaleB.mat")['Y'].reshape(-1)

def start_matlab():
    print("\nStarting MATLAB engine...")
    print("-------------------------")
    start_time = time.time()
    
    eng = matlab.engine.start_matlab()
    eng.cd("./SSC_ADMM_v1.1")

    print("Elapsed: {0:.2f} sec".format(time.time()-start_time))
    
    return eng

def load_YaleB(path='./data/CroppedYale'):
    print("\nLoading YaleB...")
    print("----------------")
    start_time = time.time()

    train, test, img_size = img2matrix.batch_convert_YaleB(path, truncate_num=38, images_per_person=None)
    images_full = train[0]
    labels = train[1]
    images_raw = images_full[:, :32256]
    images_dsift = images_full[:, 32256:]

    print("Elapsed: {0:.2f} sec".format(time.time()-start_time))

    return images_dsift, labels

def preprocess(images_dsift):
    print("\nPerforming PCA...")
    print("-----------------")
    start_time = time.time()
    
    # Perform PCA
    pca = PCA(n_components=300, whiten=False, svd_solver='arpack', random_state=0)
    images_pca = pca.fit_transform(images_dsift)

    print("Elapsed: {0:.2f} sec".format(time.time()-start_time))


    print("\nNormalizing data...")
    print("-------------------")
    start_time = time.time()

    # Normalize PCA output
    mmin = np.min(images_pca)
    mmax = np.max(images_pca)
    images_norm = (2*images_pca - mmax - mmin) / (mmax - mmin)

    print("Elapsed: {0:.2f} sec".format(time.time()-start_time))

    return images_norm

def run_model(images_norm,
              labels,
              epochs_pretrain = 101,
              epochs = 101,
              lr_pretrain = 0.08,
              lr = 0.006,
              alpha1 = 20,
              maxIter1 = 6,
              lambda1 = 0.0001,
              lambda2 = 0.001,
              alpha2 = 20,
              maxIter2 = 16):
    print("\nFinding affinity matrix (iter: {0:d})...".format(maxIter1))
    print("--------------------------")
    start_time = time.time()

    # Calculate C matrix
    # Matlab SSC #1
    savemat('./temp/temp.mat', mdict={'X': images_norm})
    k = len(np.unique(labels))
    eng.SSC_modified(k, 0, False, float(alpha1), False, 1, 1e-20, int(maxIter1))
    C = loadmat("./temp/temp.mat")['C']

    print("Elapsed: {0:.2f} sec".format(time.time()-start_time))


    print("\nTraining Autoencoder...")
    print("-----------------------")
    start_time = time.time()

    # Train Autoencoder
    d = dsc.DeepSubspaceClustering(images_norm, C=C, hidden_dims=[200, 150, 200], lambda1=lambda1, lambda2=lambda2, learning_rate=lr,
                                   weight_init='sda-uniform', weight_init_params=[epochs_pretrain, lr_pretrain, images_norm.shape[0], 100],
                                   optimizer='Adam', decay='sqrt', sda_optimizer='Adam', sda_decay='sqrt')
    d.train(batch_size=images_norm.shape[0], epochs=epochs, print_step=25)
    images_HM2 = d.result

    print("Elapsed: {0:.2f} sec".format(time.time()-start_time))


    print("\nClustering with SSC (iter: {0:d})...".format(maxIter2))
    print("----------------------")
    start_time = time.time()
    
    # Cluster
    # Matlab SSC #2
    savemat('./temp/temp.mat', mdict={'X': images_HM2})
    grps = eng.SSC_modified(k, 0, False, float(alpha2), False, 1, 1e-20, int(maxIter2))
    labels_pred = np.asarray(grps, dtype=np.int32).flatten()

    print("Elapsed: {0:.2f} sec\n".format(time.time()-start_time))

    # Evaluate
    return 1-err_rate(labels, labels_pred), nmi(labels, labels_pred, average_method="geometric"), ari(labels, labels_pred)
