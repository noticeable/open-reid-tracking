from __future__ import print_function, absolute_import
import os.path as osp
import numpy as np

from ..utils.data import Dataset
from ..utils.osutils import mkdir_if_missing
from ..utils.serialization import read_json, write_json


def _pluck(identities, indices, relabel=False):
    ret = []
    for index, pid in enumerate(indices):
        pid_images = identities[pid]
        for camid, cam_images in enumerate(pid_images):
            for fname in cam_images:
                name = osp.splitext(fname)[0]
                # x, y, _ = map(int, name.split('_'))
                name_parts = name.split('_')
                if len(name_parts) == 5:
                    x, _, _, _, y = name_parts
                else:
                    x, y, _ = name_parts
                x = int(x)
                if 'c' in y and len(name_parts) == 3:
                    y = int(y.split('c')[-1]) - 1
                else:
                    y = int(y)

                if len(name_parts) == 3:
                    assert pid == x and camid == y
                # keep intergrity of the trainval set
                if relabel:
                    ret.append((fname, index, camid))
                else:
                    ret.append((fname, pid, camid))
    return ret


class DukeMyGT(Dataset):

    def __init__(self, root, split_id=0, num_val=10, download=True, iCams=list(range(1, 9)), fps=60):
        super(DukeMyGT, self).__init__(root, split_id=split_id)

        camstyle_path = '/home/wangzd/Data/DukeMTMC/ALL_gt_bbox/gt_bbox_6_fps/allcam_camstyle_stargan4reid'
        self.camstyle = []
        MTMC_dir = '/home/wangzd/Data/DukeMTMC/ALL_gt_bbox'
        if download:
            self.download(iCams, fps, MTMC_dir, camstyle_path)

        # if not self._check_integrity():
        #     raise RuntimeError("Dataset not found or corrupted. " +
        #                        "You can use download=True to download it.")

        self.load(num_val)

    def download(self, iCams, fps, MTMC_dir, camstyle_path):
        # if self._check_integrity():
        #     print("Files already downloaded and verified")
        #     return

        import re
        import hashlib
        import shutil
        from glob import glob
        from zipfile import ZipFile

        market_raw_dir = osp.join(self.root, 'market_raw')
        mkdir_if_missing(market_raw_dir)
        # Download the raw zip file
        fpath = osp.join(market_raw_dir, 'Market-1501-v15.09.15.zip')
        # Extract the file
        exdir = osp.join(market_raw_dir, 'Market-1501-v15.09.15')
        if not osp.isdir(exdir):
            print("Extracting zip file")
            with ZipFile(fpath) as z:
                z.extractall(path=market_raw_dir)

        # Format
        images_dir = osp.join(self.root, 'images')
        mkdir_if_missing(images_dir)
        duke_raw_dir = osp.join(MTMC_dir, ('gt_bbox_' + str(fps) + '_fps'))

        # 1501 identities (+1 for background) with 6 camera views each
        # and more than 7000 ids from dukemtmc
        identities = [[[] for _ in range(8 + 6)] for _ in range(10000)]

        fake_identities = [[[] for _ in range(8)] for _ in range(8000)]

        def market_register(subdir, pattern=re.compile(r'([-\d]+)_c(\d)')):
            fpaths = sorted(glob(osp.join(exdir, subdir, '*.jpg')))
            pids = set()
            for fpath in fpaths:
                fname = osp.basename(fpath)
                pid, cam = map(int, pattern.search(fname).groups())
                if pid == -1: continue  # junk images are just ignored
                assert 0 <= pid <= 1501  # pid == 0 means background
                assert 1 <= cam <= 6
                cam = cam - 1 + 8
                pid += 8000
                pids.add(pid)
                fname = ('{:08d}_{:02d}_{:04d}.jpg'.format(pid, cam, len(identities[pid][cam])))
                identities[pid][cam].append(fname)
                shutil.copy(fpath, osp.join(images_dir, fname))
            return pids

        def duke_register(subdir, pattern=re.compile(r'([-\d]+)_c(\d)')):
            pids = set()
            for iCam in iCams:
                cam_dir = 'camera' + str(iCam)
                fpaths = sorted(glob(osp.join(subdir, cam_dir, '*.jpg')))
                for fpath in fpaths:
                    copy_flag = 1
                    fname = osp.basename(fpath)
                    pid, cam = map(int, pattern.search(fname).groups())
                    if pid == -1: continue  # junk images are just ignored
                    assert 0 <= pid <= 8000  # pid == 0 means background
                    assert 1 <= cam <= 8
                    cam -= 1  # from range[1,8]to range[0,7]
                    pids.add(pid)
                    # fname = ('{:08d}_{:02d}_{:04d}.jpg'.format(pid, cam, len(identities[pid][cam])))
                    identities[pid][cam].append(fname)
                    # only copy once
                    if osp.isfile(osp.join(images_dir, fname)) and copy_flag:
                        copy_flag = 0
                    if copy_flag:
                        shutil.copy(fpath, osp.join(images_dir, fname))
                pass
            return pids

        def fake_register(subdir, trainval_pids):
            pids = set()
            pid_pattern = re.compile(r'([-\d]+)_c(\d)')
            cam_pattern = re.compile(r'fake_(\d)')  # use fakes transferred to iCam style
            fpaths = sorted(glob(osp.join(subdir, '*.jpg')))
            for fpath in fpaths:
                copy_flag = 1
                fname = osp.basename(fpath)
                pid, source_cam = map(int, pid_pattern.search(fname).groups())
                fake_cam = int(cam_pattern.search(fname).groups()[0])

                if pid == -1: continue  # junk images are just ignored
                if fake_cam == source_cam: continue  # skip self transformed imgs
                if pid not in trainval_pids: continue  # skip imgs not in trainval
                if fake_cam not in iCams: continue  # skip imgs not belong to iCams list

                assert 0 <= pid <= 8000  # pid == 0 means background
                assert 1 <= fake_cam <= 8
                fake_cam -= 1  # from range[1,8]to range[0,7]
                pids.add(pid)
                # fname = ('{:08d}_{:02d}_{:04d}.jpg'.format(pid, cam, len(identities[pid][cam])))
                fake_identities[pid][fake_cam].append(fname)
                # only copy once
                if osp.isfile(osp.join(images_dir, fname)) and copy_flag:
                    copy_flag = 0
                if copy_flag:
                    shutil.copy(fpath, osp.join(images_dir, fname))
            pass

            return pids

        trainval_pids = duke_register(duke_raw_dir)
        gallery_pids = market_register('bounding_box_test')
        query_pids = market_register('query')
        camstyle_pids = fake_register(camstyle_path, trainval_pids)
        assert query_pids <= gallery_pids
        assert trainval_pids.isdisjoint(gallery_pids)

        # Save meta information into a json file
        meta = {'name': 'DukeMyGT', 'shot': 'multiple', 'num_cameras': 14,
                'identities': identities}
        write_json(meta, osp.join(self.root, 'meta.json'))

        fake_meta = {'name': 'DukeCamStyleFake', 'shot': 'multiple', 'num_cameras': 14,
                'fake_identities': fake_identities}
        write_json(fake_meta, osp.join(self.root, 'fake_meta.json'))

        # Save the only training / test split
        splits = [{
            'trainval': sorted(list(trainval_pids)),
            'query': sorted(list(query_pids)),
            'gallery': sorted(list(gallery_pids)),
            'camstyle': sorted(list(camstyle_pids))
        }]
        write_json(splits, osp.join(self.root, 'splits.json'))

    def load(self, num_val=0.3, verbose=True):
        splits = read_json(osp.join(self.root, 'splits.json'))
        if self.split_id >= len(splits):
            raise ValueError("split_id exceeds total splits {}"
                             .format(len(splits)))
        self.split = splits[self.split_id]

        # Randomly split train / val
        trainval_pids = np.asarray(self.split['trainval'])
        np.random.shuffle(trainval_pids)
        num = len(trainval_pids)
        if isinstance(num_val, float):
            num_val = int(round(num * num_val))
        if num_val >= num or num_val < 0:
            raise ValueError("num_val exceeds total identities {}"
                             .format(num))
        if num_val:
            train_pids = sorted(trainval_pids[:-num_val])
            val_pids = sorted(trainval_pids[-num_val:])
        else:
            train_pids = sorted(trainval_pids)
            val_pids = sorted([])

        self.meta = read_json(osp.join(self.root, 'meta.json'))
        identities = self.meta['identities']
        self.fake_meta = read_json(osp.join(self.root, 'fake_meta.json'))
        fake_identities = self.fake_meta['fake_identities']
        self.train = _pluck(identities, train_pids, relabel=True)
        self.val = _pluck(identities, val_pids, relabel=True)
        self.trainval = _pluck(identities, trainval_pids, relabel=True)
        self.query = _pluck(identities, self.split['query'])
        self.gallery = _pluck(identities, self.split['gallery'])
        self.camstyle = _pluck(fake_identities, self.split['camstyle'], relabel=True)
        self.num_train_ids = len(train_pids)
        self.num_val_ids = len(val_pids)
        self.num_trainval_ids = len(trainval_pids)

        if verbose:
            print(self.__class__.__name__, "dataset loaded")
            print("  subset   | # ids | # images")
            print("  ---------------------------")
            print("  train    | {:5d} | {:8d}"
                  .format(self.num_train_ids, len(self.train)))
            print("  val      | {:5d} | {:8d}"
                  .format(self.num_val_ids, len(self.val)))
            print("  trainval | {:5d} | {:8d}"
                  .format(self.num_trainval_ids, len(self.trainval)))
            print("  query    | {:5d} | {:8d}"
                  .format(len(self.split['query']), len(self.query)))
            print("  gallery  | {:5d} | {:8d}"
                  .format(len(self.split['gallery']), len(self.gallery)))
            print("  camstyle  | {:5d} | {:8d}"
                  .format(len(self.split['camstyle']), len(self.camstyle)))
