#!/usr/bin/env python
""" Handler Class for Data Files
    - [QuantizeDataHandler]: Quantize the features in the Data
    it also includes a depreciated version of hanlder class for flow file generated by fs-simulator [DataFile]
"""
__author__ = "Jing Conan Wang"
__email__ = "wangjing@bu.edu"

# import sys; sys.path.append("..")
from ClusterAlg import KMeans, KMedians
from DetectorLib import vector_quantize_states, model_based, model_free
from util import DF, NOT_QUAN, QUAN
from util import abstract_method, FetchNoDataException

from DataHandler_deprec import DataFile
##############################################################
####                  Interface Class                   ######
##############################################################
class DataHandler(object):
    """virtual base class for Data Hanlder. Data Handler contains one or more
    Data class as the data source. And it generate the emperical measure based
    on the data class.
    """
    def get_em(self, rg=None, rg_type='time'):
        """get emperical measure within a range. emeprical measure is used to
        represent the data in this range. For example, it can the probability
        distribution of flow quantization state within and range(*for the model
        free case*), or the markovian trantion probability for the *model based*
        case"""
        abstract_method()

from socket import inet_ntoa
from struct import pack
def long_to_dotted(ip):
    ip_addr = inet_ntoa(pack('!L', ip))
    return [int(val) for val in ip_addr.rsplit('.')]

from DetectorLib import get_feature_hash_list
class QuantizeDataHandler(object):
    """Quantize the feature in the Data"""
    def __init__(self, data, fr_win_size=None, fea_option=None):
        self._init_data(data)
        self.fr_win_size = fr_win_size
        self.fea_option  = fea_option
        self.direct_fea_list = [ k for k in fea_option.keys() if k not in ['cluster', 'dist_to_center']]
        self.fea_QN = [fea_option['cluster'], fea_option['dist_to_center']] + [fea_option[k] for k in self.direct_fea_list]

        self._cluster_src_ip(fea_option['cluster'])
        self._set_fea_range()

    def _init_data(self, data):
        self.data = data

    def _to_dotted(self, ip):
        if isinstance(ip, str):
            return tuple( [int(v) for v in ip.rsplit('.')] )
        elif isinstance(ip, long):
            return long_to_dotted(int(ip))

    def _cluster_src_ip(self, cluster_num):
        src_ip_int_vec_tmp = self.data.get_fea_slice(['src_ip']) #FIXME, need to only use the training data
        src_ip_str_vec = [x[0] for x in src_ip_int_vec_tmp]
        print 'finish get ip address'
        unique_src_IP_str_vec_set = list( set( src_ip_str_vec ) )
        unique_src_IP_vec_set = [self._to_dotted(ip) for ip in unique_src_IP_str_vec_set]
        # print 'start kmeans...'
        # unique_src_cluster, center_pt = KMeans(unique_src_IP_vec_set, cluster_num, DF)
        unique_src_cluster, center_pt = KMedians(unique_src_IP_vec_set, cluster_num, DF)
        self.cluster_map = dict(zip(unique_src_IP_str_vec_set, unique_src_cluster))
        # self.center_map = dict(zip(unique_src_IP_vec_set, center_pt))
        dist_to_center = [DF( unique_src_IP_vec_set[i], center_pt[ unique_src_cluster[i] ]) for i in xrange(len(unique_src_IP_vec_set))]
        self.dist_to_center_map = dict(zip(unique_src_IP_str_vec_set, dist_to_center))

    def _set_fea_range(self):
        """set the global range for the feature list, used for quantization"""
        # set global fea range
        min_dist_to_center = min(self.dist_to_center_map.values())
        max_dist_to_center = max(self.dist_to_center_map.values())

        min_vec = self.data.get_min(self.direct_fea_list)
        max_vec = self.data.get_max(self.direct_fea_list)

        self.global_fea_range = [
                [0, min_dist_to_center] + min_vec,
                [self.fea_option['cluster']-1, max_dist_to_center] + max_vec,
                ]

    def get_fea_list(self):
        return ['cluster', 'dist_to_center'] + self.direct_fea_list

    def get_fea_slice(self, rg=None, rg_type=None):
        """get a slice of feature. it does some post-processing after get feature
        slice from Data. First it get *direct_fea_vec* from data, which is defined
        in **self.direct_fea_list**. then it cluster
        the source ip address, and insert the cluster label and distance to the
        cluster center to the feature list.
        """
        # get direct feature
        direct_fea_vec = self.data.get_fea_slice(self.direct_fea_list, rg, rg_type)
        if not direct_fea_vec:
            raise FetchNoDataException("Didn't find any data in this range")

        # calculate indirect feature
        src_ip_tmp = self.data.get_fea_slice(['src_ip'], rg, rg_type)
        src_ip = [x[0] for x in src_ip_tmp]
        fea_vec = []
        for i in xrange(len(src_ip)):
            ip = src_ip[i]
            fea_vec.append( [self.cluster_map[ip], self.dist_to_center_map[ip]] + [float(x) for x in direct_fea_vec[i]])

        # min_vec = self.data.get_min(self.direct_fea_list, rg, rg_type)
        # max_vec = self.data.get_max(self.direct_fea_list, rg, rg_type)

        # dist_to_center_vec = [self.dist_to_center_map[ip] for ip in src_ip]
        # min_dist_to_center = min(dist_to_center_vec)
        # max_dist_to_center = max(dist_to_center_vec)

        # fea_range = [
        #         [0, min_dist_to_center] + min_vec,
        #         [self.fea_option['cluster']-1, max_dist_to_center] + max_vec,
        #         ]

        # quan_flag specify whether a data need to be quantized or not.
        self.quan_flag = [QUAN] * len(self.fea_option.keys())
        self.quan_flag[0] = NOT_QUAN
        # return fea_vec, fea_range
        return fea_vec

    def get_em(self, rg=None, rg_type=None):
        """get empirical measure"""
        q_fea_vec = self.quantize_fea(rg, rg_type )
        pmf = model_free( q_fea_vec, self.fea_QN )
        Pmb, mpmb = model_based( q_fea_vec, self.fea_QN )
        return pmf, Pmb, mpmb

    def quantize_fea(self, rg=None, rg_type=None):
        """get quantized features for part of the flows"""
        # fea_vec, fea_range = self.get_fea_slice(rg, rg_type)
        fea_vec = self.get_fea_slice(rg, rg_type)
        q_fea_vec = vector_quantize_states(zip(*fea_vec), self.fea_QN, zip(*self.global_fea_range), self.quan_flag)
        return q_fea_vec

    def hash_quantized_fea(self, rg, rg_type):
        q_fea_vec = self.quantize_fea(rg, rg_type)
        return get_feature_hash_list(q_fea_vec, self.fea_QN)
