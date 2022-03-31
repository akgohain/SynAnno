'''
*********   Project: SynAnno for synapse annnotation in EM volumes   ********

Directory structure:
.
|__Images
|__Syn;                                         |__Img;       
  |__ Directories named as synapse indexes        |__Directories named as synapse indexes   
    |_label.tif                                     |_image.tif

Metadata JSON file structure:
{
    "Data": [
        {
            "Image_Name": "image.tif",  # image volume filename
            "Label_Name": "label.tif",  # label volume filename
            "Image_Index": 1,           # synapse index (int)
            "GT": ".\Images\Syn\1",     # folder containing GT images.
            "EM": ".\Images\Img\1",     # folder containing EM images.
            "Correct": "Yes",           # default
            "Annotated": "No",          # default
            "Middle_Slice": 7,          # middle slice of the 3D volume containing synapse
            "Rotation_Info": 67.0       # rotation_angle
            "Original_Bbox": []         # original bounding box
            "Adjusted_Bbox": []         # adjust boundind box based on crop size    
            "Padding": []               # padding size for y and x axes
        },
        *** Similarly for all other synapses ***
    ]
}
'''

import os
import json
import errno
import imageio
import warnings
import itertools
import numpy as np
from scipy import stats
from skimage.morphology import binary_dilation, remove_small_objects
from skimage.measure import label as label_cc

from .utils import *

# Processing the synpases using binary dilation as well as by removing small objects.
def process_syn(gt, small_thres=16):
    indices = np.unique(gt)
    is_semantic = len(indices) == 3 and (indices==[0,1,2]).all()
    if not is_semantic: # already an instance-level segmentation
        syn, seg = gt, (gt.copy() + 1) // 2
        return syn, seg

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=UserWarning)
        seg = binary_dilation(gt.copy() != 0)
        seg = label_cc(seg).astype(int)
        seg = seg * (gt.copy() != 0).astype(int)
        seg = remove_small_objects(seg, small_thres)

        c2 = (gt.copy() == 2).astype(int)
        c1 = (gt.copy() == 1).astype(int)

        syn_pos = np.clip((seg * 2 - 1), a_min=0, a_max=None) * c1
        syn_neg = (seg * 2) * c2
        syn = np.maximum(syn_pos, syn_neg)

    return syn, seg


def bbox2_ND(img):
    N = img.ndim
    out = []
    for ax in itertools.combinations(reversed(range(N)), N - 1):
        nonzero = np.any(img, axis=ax)
        out.extend(np.where(nonzero)[0][[0, -1]])
    return tuple(out)


def adjust_bbox(low, high, sz):
    assert high >= low
    bbox_sz = high - low
    diff = abs(sz - bbox_sz) // 2
    if bbox_sz >= sz:
        return low + diff, low + diff + sz

    return low - diff, low - diff + sz


# crop a 2D patch from 3D volume
def crop_pad_data(data, z, bbox_2d, pad_val=0, mask=None, return_box=False):
    sz = data.shape[1:]
    y1o, y2o, x1o, x2o = bbox_2d  # region to crop
    y1m, y2m, x1m, x2m = 0, sz[0], 0, sz[1]
    y1, x1 = max(y1o, y1m), max(x1o, x1m)
    y2, x2 = min(y2o, y2m), min(x2o, x2m)
    cropped = data[z, y1:y2, x1:x2]

    if mask is not None:
        mask_2d = mask[z, y1:y2, x1:x2]
        cropped = cropped * (mask_2d != 0).astype(cropped.dtype)

    pad = ((y1 - y1o, y2o - y2), (x1 - x1o, x2o - x2))
    if not all(v == 0 for v in pad):
        cropped = np.pad(cropped, pad, mode='constant',
                         constant_values=pad_val)

    if not return_box:
        return cropped

    return cropped, [y1, y2, x1, x2], pad


def syn2rgb(label):
    tmp = [None] * 3
    tmp[0] = np.logical_and((label % 2) == 1, label > 0)
    tmp[1] = np.logical_and((label % 2) == 0, label > 0)
    tmp[2] = (label > 0)
    out = np.stack(tmp, -1).astype(np.uint8) # shape is (*, 3)
    return out * 255


# create a directory if it does not exist
def create_dir(parent_dir_path, dir_name):
    dir_path = os.path.join(parent_dir_path, dir_name)
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
    return dir_path


# calculate the rotation angle to align masks with different orientations
def calculate_rot(syn, struct_sz=3, return_overlap=False, mode='linear'):
    assert mode in ['linear', 'siegel', 'theil']
    struct = np.ones((struct_sz, struct_sz), np.uint8)
    pos = binary_dilation(np.logical_and((syn % 2) == 1, syn > 0), struct)
    neg = binary_dilation(np.logical_and((syn % 2) == 0, syn > 0), struct)
    overlap = pos.astype(np.uint8) * neg.astype(np.uint8)
    if overlap.sum() <= 20: # (almost) no overlap
        overlap = (syn!=0).astype(np.uint8)

    pt = np.where(overlap != 0)
    if mode == 'linear':
        slope, _, _, _, _ = stats.linregress(pt[0], pt[1])
    elif mode == 'siegel':
        slope, _ = stats.siegelslopes(pt[1], pt[0])
    elif mode == 'theil':
        slope, _, _, _ = stats.theilslopes(pt[1], pt[0])
    else:
        raise ValueError("Unknown mode %s in regression." % mode)
        
    angle = np.arctan(slope) / np.pi * 180
    if return_overlap:
        return angle, slope, overlap
    
    return angle, slope


def visualize(syn, seg, img, sz, return_data=False):
    crop_size = int(sz * 1.415) # considering rotation 
    item_list, data_dict = [], {}
    seg_idx = np.unique(seg)[1:] # ignore background
    
    idx_dir = create_dir('./static/', 'Images')
    syn_folder, img_folder = create_dir(idx_dir, 'Syn'), create_dir(idx_dir, 'Img')
    
    # iterate over the synapses. save the middle slices and before/after ones for navigation.
    for idx in seg_idx:
        syn_all, img_all = create_dir(syn_folder, str(idx)), create_dir(img_folder, str(idx))

        # create a new item for the JSON file with defaults.
        item = dict()
        item["Image_Name"] = 'image.tif'
        item["Label_Name"] = 'label.tif'
        item["Image_Index"] = int(idx)
        item["GT"] = syn_all.strip(".\\")
        item["EM"] = img_all.strip(".\\")
        item["Label"] = "Correct"
        item["Annotated"] = "No"            
        
        temp = (seg == idx) # binary mask of the current synapse
        bbox = bbox2_ND(temp)
        
        z_mid = (bbox[0] + bbox[1]) // 2 # middle slice in 3D volume
        item["Middle_Slice"] = str(z_mid)
        item["Original_Bbox"] = [int(u) for u in list(bbox)]

        temp_2d = temp[z_mid]      
        bbox_2d = bbox2_ND(temp_2d)    

        y1, y2 = adjust_bbox(bbox_2d[0], bbox_2d[1], crop_size)
        x1, x2 = adjust_bbox(bbox_2d[2], bbox_2d[3], crop_size)
        crop_2d = [y1, y2, x1, x2]

        cropped_syn, syn_bbox, padding = crop_pad_data(syn, z_mid, crop_2d, mask=temp, return_box=True)
        cropped_img = crop_pad_data(img, z_mid, crop_2d, pad_val=128)

        # calculate the padding for frontend display, later used for unpadding.
        item["Adjusted_Bbox"] = [bbox[0], bbox[1]] + syn_bbox
        item["Padding"] = padding

        # calculate and save the angle of rotation.
        angle, _ = calculate_rot(cropped_syn, return_overlap=False, mode='linear')

        img_dtype, syn_dtype = cropped_img.dtype, cropped_syn.dtype
        rotate_img_zmid, rotate_syn_zmid, angle = rotateIm_polarity(
            cropped_img.astype(np.float32), cropped_syn.astype(np.float32), -angle)
        rotate_img_zmid = center_crop(rotate_img_zmid.astype(img_dtype), sz)
        rotate_syn_zmid = center_crop(rotate_syn_zmid.astype(syn_dtype), sz)

        item["Rotation_Angle"] = angle
        item_list.append(item)

        image_list, label_list = [], []
        for z_index in range(bbox[0], bbox[1]+1):
            if z_index == z_mid:
                image_list.append(rotate_img_zmid)
                label_list.append(rotate_syn_zmid)
                continue

            cropped_syn = crop_pad_data(syn, z_index, crop_2d, mask=temp)
            cropped_img = crop_pad_data(img, z_index, crop_2d, pad_val=128)
            rotate_img = rotateIm(cropped_img.astype(np.float32), angle, target_type='img')
            rotate_syn = rotateIm(cropped_syn.astype(np.float32), angle, target_type='mask')

            image_list.append(center_crop(rotate_img.astype(img_dtype), sz))
            label_list.append(center_crop(rotate_syn.astype(img_dtype), sz))

        vis_image = np.stack(image_list, 0)
        vis_label = syn2rgb(np.stack(label_list, 0)) # z, y, x, c
        data_dict[idx] = [vis_image, vis_label]

        if not return_data:
            imageio.volwrite(os.path.join(img_all, "image.tif"), vis_image)
            imageio.volwrite(os.path.join(syn_all, "label.tif"), vis_label)
        
    if return_data:
        return data_dict

    # create and export the JSON File
    final_file = dict()
    final_file["Data"] = item_list
    json_obj = json.dumps(final_file, indent=4, cls=NpEncoder)
    with open("synAnno.json", "w") as outfile:
        outfile.write(json_obj)


def load_3d_files(im_file, gt_file, patch_size=142):
    gt = readvol(gt_file)  # The mask annotation (GT: ground truth)
    im = readvol(im_file)  # The original image (EM)

    if gt.ndim != 3:
        # If the gt is not segmentation mask but predicted polarity, generate
        # the individual synapses using the polarity2instance function from
        # https://github.com/zudi-lin/pytorch_connectomics/blob/master/connectomics/utils/process.py
        assert (gt.ndim == 4 and gt.shape[0] == 3)
        warnings.warn("Converting polarity prediction into segmentation, which can be very slow!")
        scales = (im.shape[0]/gt.shape[1], im.shape[1]/gt.shape[2], im.shape[2]/gt.shape[3])
        gt = polarity2instance(gt.astype(np.uint8), semantic=False, scale_factors=scales)

    # Processing the 3D volume to get 2D patches.
    syn, seg = process_syn(gt)
    visualize(syn, seg, im, sz=patch_size, rgb=True)
    
    synanno_json = os.path.join('.', 'synAnno.json')
    if os.path.isfile(synanno_json):
        return synanno_json
    else:
        raise FileNotFoundError(
            errno.ENOENT, os.strerror(errno.ENOENT), 'synAnno.json')
