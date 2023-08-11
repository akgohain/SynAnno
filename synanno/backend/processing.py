from typing import Union, Tuple, Dict

import os
import json
import shutil
import traceback
import numpy as np
from PIL import Image
from skimage.morphology import remove_small_objects
from skimage.measure import label as label_cc
from skimage.transform import resize
from scipy.ndimage import find_objects, center_of_mass

from .utils import *


import synanno # import global configs
from synanno import app # import the package app

from cloudvolume import CloudVolume, Bbox
import pandas as pd

from flask import session

from concurrent.futures import ThreadPoolExecutor, as_completed


def process_syn(gt: np.ndarray) -> np.ndarray:
    """Process the ground truth segmentation.

    Args:
        gt (np.ndarray): the ground truth segmentation.
        small_thres (int): the threshold for removing small objects.

    Returns:
        seg (np.ndarray): the processed segmentation.
    """

    # convert the semantic segmentation to instance-level segmentation
    # assign each synapse a unique index
    seg = label_cc(gt).astype(int)
    # identify the largest connected component in the center of the volume and mask out the rest
    center_blob_value = get_center_blob_value_vectorized(seg, np.unique(seg)[1:])
    seg *= (seg == center_blob_value)
    return seg


def get_center_blob_value_vectorized(labeled_array: np.ndarray, blob_values: np.ndarray) -> int:
    ''' Get the value of the non-zero blob closest to the center of the labeled array.
    
    Args:
        labeled_array (np.ndarray): 3D numpy array where different blobs are represented by different integers.
        blob_values (np.ndarray): Array of unique blob values in the labeled_array.
        
    Returns:
        center_blob_value (int): Value of the center blob.
    '''
    # Calculate the center of the entire array
    array_center = np.array(labeled_array.shape) / 2.0

    # Create a 4D array where the first dimension is equal to the number of blobs
    # and the last three dimensions are equal to the dimensions of the original array
    blob_masks = np.equal.outer(blob_values, labeled_array)

    # Compute the center of mass for each blob
    blob_centers = np.array([center_of_mass(mask) for mask in blob_masks])

    # Calculate the distance from each blob center to the array center
    distances = np.linalg.norm(blob_centers - array_center, axis=1)

    # Find the index of the blob with the minimum distance
    center_blob_index = np.argmin(distances)

    # Return the value of the blob with the minimum distance
    return blob_values[center_blob_index]


def calculate_crop_pad(bbox_3d: list, volume_shape: tuple, pad_z: bool = False) -> Tuple[list, tuple]:
    """Calculate the crop and pad parameters for the given bounding box and volume shape.
    
    Args:
        bbox_3d (list): the bounding box of the 3D volume.
        volume_shape (tuple): the shape of the 3D volume.
        pad_z (bool): whether to pad the z dimension.

    Returns:
        bbox (list): the bounding box of the 3D volume.
        pad (tuple): the padding parameters.

    """
    c11o, c12o, c21o, c22o, c31o, c32o = bbox_3d  # region to crop
    c11m, c12m, c21m, c22m, c31m, c32m = 0, volume_shape[0], 0, volume_shape[1], 0, volume_shape[2]
    c11, c21, c31 = max(c11o, c11m), max(c21o, c21m), max(c31o, c31m)
    c12, c22, c32 = min(c12o, c12m), min(c22o, c22m), min(c32o, c32m)

    assert c11 < c12 and c21 < c22 and c31 < c32, "Invalid bounding box."

    pad = [[c11 - c11o, c12o - c12], [c21 - c21o, c22o - c22], [c31 - c31o, c32o - c32]]

    if not pad_z:
        pad[list(synanno.coordinate_order.keys()).index('z')] = [0, 0]

    return [c11, c12, c21, c22, c31, c32], pad


def create_dir(parent_dir_path: str, dir_name: str) -> str:
    ''' Create a directory if it does not exist.
    
    Args:
        parent_dir_path (str): the path to the parent directory.
        dir_name (str): the name of the directory.
        
    '''
    dir_path = os.path.join(parent_dir_path, dir_name)
    if not os.path.exists(dir_path):
        os.makedirs(dir_path)
    return dir_path


def syn2rgb(label: np.ndarray) -> np.ndarray:
    ''' Convert the binary mask of the synapse to RGB format.
    
    Args:
        label (np.ndarray): the binary mask of the synapse.
        
    Returns:
        out (np.ndarray): the RGB mask of the synapse.
    '''
    tmp = [None] * 3
    tmp[0] = tmp[2] = (label > 0)
    tmp[1] = np.zeros_like(label)
    out = adjust_image_range(np.stack(tmp, -1)) # shape is (*, 3))
    return out

def free_page() -> None:
    ''' Remove the segmentation and images from the EM and GT folder for the previous and next page.'''

    # create the handles to the directories
    base_folder = os.path.join(os.path.join(app.config['PACKAGE_NAME'], app.config['STATIC_FOLDER']), 'Images')
    syn_dir, img_dir = os.path.join(base_folder, 'Syn'), os.path.join(base_folder, 'Img')

    # retrieve the image index for all instances that are not labeled as "Correct"
    key_list = synanno.df_metadata.query('Label == "Correct"')["Image_Index"].values.tolist()

    # remove the segmentation and images from the EM and GT folder for the previous and next page.
    for key in key_list:
                
        # remove the segmentation and images from the EM and GT folder for the previous page.
        syn_dir_idx = os.path.join(syn_dir, str(key))
        img_dir_idx = os.path.join(img_dir, str(key))

        if os.path.exists(syn_dir_idx):
            try:
                shutil.rmtree(syn_dir_idx)
            except Exception as e:
                print('Failed to delete %s. Reason: %s' % (syn_dir_idx, e))
        if os.path.exists(img_dir_idx):
            try:
                shutil.rmtree(img_dir_idx)
            except Exception as e:
                print('Failed to delete %s. Reason: %s' % (img_dir_idx, e))
    

def retrieve_instance_metadata(crop_size_x: int = 148, crop_size_y: int = 148, crop_size_z: int = 16, page: int =0, mode: str = 'annotate') -> Union[str, None]:
    ''' Visualize the synapse and EM images in 2D slices for each instance by cropping the bounding box of the instance.
        Processing each instance individually, retrieving them from the cloud volume and saving them to the local disk.
    
    Args:
        crop_size_x (int): the size of the 2D patch in x direction.
        crop_size_y (int): the size of the 2D patch in y direction.
        crop_size_z (int): the size of the 2D patch in z direction.
        page (int): the current page number for which to compute the data.
        
    Returns:
        synanno_json (str): the path to the JSON file.
    '''

    # create the handles to materialization data object
    global materialization

    # retrieve the order of the coordinates (xyz, xzy, yxz, yzx, zxy, zyx)
    coordinate_order = list(synanno.coordinate_order.keys())

    # set the progress bar to zero
    if page != 0:      
        synanno.progress_bar_status['percent'] = 0
        synanno.progress_bar_status['status'] = f"Loading page {str(page)}."

    # create the directories for saving the source and target images
    idx_dir = create_dir('./synanno/static/', 'Images')
    syn_dir, img_dir = create_dir(idx_dir, 'Syn'), create_dir(idx_dir, 'Img')

    if synanno.df_metadata.query('Page == @page').empty:

        # retrieve the meta data for the synapses associated with the current page
        bbox_dict = get_sub_dict_within_range(materialization, (page * session['per_page']), session['per_page'] + (page * session['per_page']) - 1)

        # collect the instances to only write to the metadata frame once
        instance_list = []

        ### iterate over the synapses. save the middle slices and before/after ones for navigation. ###
        for i, idx in enumerate(bbox_dict.keys()):

            synanno.progress_bar_status['status'] = f"Inst.{str(idx)}: Calculate bounding box."

            # create the instance specific directories for saving the source and target images
            syn_dir_instance, img_dir_instance = create_dir(syn_dir, str(idx)), create_dir(img_dir, str(idx))

            ### Note that all dimensions are saved in then scale of the target (segmentation) volume. ###

            # create a new item
            item = dict()
            item["Page"] = int(page)
            item["Image_Index"] = int(idx)
            item["GT"] = "/"+"/".join(syn_dir_instance.strip(".\\").split("/")[2:])
            item["EM"] = "/"+"/".join(img_dir_instance.strip(".\\").split("/")[2:])
            item["Label"] = "Correct"
            item["Annotated"] = "No"            
            item["Error_Description"] = "None"
            item["X_Index"] = coordinate_order.index('x')
            item["Y_Index"] = coordinate_order.index('y')
            item["Z_Index"] = coordinate_order.index('z')
            item["Middle_Slice"] = int(bbox_dict[idx]['z'])
            item["cz0"] = int(bbox_dict[idx]['z'])
            item["cy0"] = int(bbox_dict[idx]['y'])
            item["cx0"] = int(bbox_dict[idx]['x'])
            item["pre_pt_x"] = int(bbox_dict[idx]['pre_pt_x'])
            item["pre_pt_y"] = int(bbox_dict[idx]['pre_pt_y'])
            item["pre_pt_z"] = int(bbox_dict[idx]['pre_pt_z'])
            item["post_pt_x"] = int(bbox_dict[idx]['post_pt_x'])
            item["post_pt_y"] = int(bbox_dict[idx]['post_pt_y'])
            item["post_pt_z"] = int(bbox_dict[idx]['post_pt_z'])
            item["crop_size_x"] = crop_size_x
            item["crop_size_y"] = crop_size_y
            item["crop_size_z"] = crop_size_z


            # retrieve the bounding box for the current synapse from the central synapse coordinates
            z1 = item["cz0"] - crop_size_z // 2
            z2 = item["cz0"] + crop_size_z // 2
            y1 = item["cy0"] - crop_size_y // 2
            y2 = item["cy0"] + crop_size_y // 2
            x1 = item["cx0"] - crop_size_x // 2
            x2 = item["cx0"] + crop_size_x // 2

            bbox_org  = list(map(int, [z1, z2, y1, y2, x1, x2]))

            # save the original bounding box using the provided coordinate order
            item["Original_Bbox"] = [bbox_org[coordinate_order.index(coord)*2 + i] for coord in ['z', 'y', 'x'] for i in range(2)]

            # retrieve the actual crop coordinates and possible padding based on the max dimensions of the whole cloud volume
            crop_bbox, img_padding = calculate_crop_pad(item["Original_Bbox"] , synanno.vol_dim)

            item["Adjusted_Bbox"], item["Padding"] = crop_bbox, img_padding
            instance_list.append(item)
        # write the instance list to the dataframe
        df_list = pd.DataFrame(instance_list)
        # concatenate the metadata and the df_list dataframe
        synanno.df_metadata = pd.concat([synanno.df_metadata, df_list], ignore_index=True)

    # retrieve the page's metadata from the dataframe
    if mode == 'annotate':
        page_metadata = synanno.df_metadata.query('Page == @page')
    elif mode == 'draw':
        page_metadata = synanno.df_metadata.query('Label != "Correct"')
    
    # sort the metadata by the image index
    page_metadata = page_metadata.sort_values(by='Image_Index').to_dict('records')  # convert dataframe to list of dicts

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:  # adjust max_workers as needed
        futures = [executor.submit(_process_instance, item, create_dir(img_dir, str(item['Image_Index'])), create_dir(syn_dir, str(item['Image_Index']))) for i, item in enumerate(page_metadata)]

        synanno.progress_bar_status['status'] = f"Pre-process sub-volume."
        synanno.progress_bar_status['percent'] = int(60) 
        for future in concurrent.futures.as_completed(futures):
            try:
                _ = future.result()
            except Exception as exc:
                print('An exception occurred: %s' % exc)
                print('Retry to process the instance.')
                try:
                    future.result(timeout=15)
                except Exception as exc:
                    print('The exception persists: %s' % exc)
                    traceback.print_exc()
            
    synanno.progress_bar_status['percent'] = int(100) 

def _process_instance(item: dict, img_dir_instance: str, syn_dir_instance: str) -> None:
    ''' Process the synapse and EM images for a single instance.

    Args:
        item (dict): the dictionary containing the metadata of the current instance.
        img_dir_instance (str): the path to the directory for saving the EM images.
        syn_dir_instance (str): the path to the directory for saving the synapse images.

    '''
    
    crop_bbox = item['Adjusted_Bbox']
    img_padding = item['Padding']
    
    # retrieve the coordinate order of the cloud volume | xyz, xzy, yxz, yzx, zxy, zyx
    coord_order = list(synanno.coordinate_order.keys())

    # map the bounding box coordinates to a dictionary using the provided coordinate order
    crop_box_dict = {
        coord_order[0]+'1': crop_bbox[0],
        coord_order[0]+'2': crop_bbox[1],
        coord_order[1]+'1': crop_bbox[2],
        coord_order[1]+'2': crop_bbox[3],
        coord_order[2]+'1': crop_bbox[4],
        coord_order[2]+'2': crop_bbox[5]
    }

    # create the bounding box for the current synapse based on the order of the coordinates
    bound_target = Bbox(
        [crop_box_dict[coord_order[i] + '1'] for i in range(3)],
        [crop_box_dict[coord_order[i] + '2'] for i in range(3)]
    )

    # scale the bounding box to the resolution of the source cloud volume
    bound_source = Bbox((bound_target.minpt * list(synanno.scale.values())).astype(int), (bound_target.maxpt * list(synanno.scale.values())).astype(int))

    # retrieve the source and target images from the cloud volume
    cropped_img = synanno.source_cv.download(bound_source, coord_resolution=synanno.coord_resolution_source, mip=0, parallel=True)
    cropped_gt = synanno.target_cv.download(bound_target, coord_resolution=synanno.coord_resolution_target, mip=0, parallel=True)

    # remove the singleton dimension, take care as the z dimension might be singleton
    cropped_img = cropped_img.squeeze(axis=3)
    cropped_gt = cropped_gt.squeeze(axis=3)

    # adjust the scale of the label volume
    if sum(cropped_img.shape) > sum(cropped_gt.shape): # up-sampling
        cropped_gt = resize(cropped_gt, cropped_img.shape, mode='constant', preserve_range=True, anti_aliasing=False)
        cropped_gt = (cropped_gt > 0.5).astype(int) # convert to binary mask
    elif sum(cropped_img.shape) < sum(cropped_gt.shape): # down-sampling
        cropped_gt = resize(cropped_gt, cropped_img.shape, mode='constant', preserve_range=True, anti_aliasing=True)
        cropped_gt = (cropped_gt > 0.5).astype(int) # convert to binary mask

    # process the 3D gt segmentation by removing small objects and converting it to instance-level segmentation.
    cropped_seg = process_syn(cropped_gt)

    # pad the images and synapse segmentation to fit the crop size (sz)
    cropped_img_pad = np.pad(cropped_img, img_padding, mode='constant', constant_values=148)
    cropped_seg_pad = np.pad(cropped_seg, img_padding, mode='constant', constant_values=0)  
    
    assert cropped_img_pad.shape == cropped_seg_pad.shape, "The shape of the source and target images do not match."

    ### mark the position of the post and pre synapses using pre_pt and post_pt

    # adjust pre_pt and post_pt to cropped out section
    pre_pt_x = item["pre_pt_x"] - crop_box_dict['x1'] + img_padding[coord_order.index('x')][0]
    pre_pt_y = item["pre_pt_y"] - crop_box_dict['y1'] + img_padding[coord_order.index('y')][0]
    pre_pt_z = item["pre_pt_z"] - crop_box_dict['z1'] + img_padding[coord_order.index('z')][0]
    
    post_pt_x = item["post_pt_x"] - crop_box_dict['x1'] + img_padding[coord_order.index('x')][0]
    post_pt_y = item["post_pt_y"] - crop_box_dict['y1'] + img_padding[coord_order.index('y')][0]
    post_pt_z = item["post_pt_z"] - crop_box_dict['z1'] + img_padding[coord_order.index('z')][0]

    # scale the the points to the resolution of the source cloud volume
    pre_pt_x = int(pre_pt_x * synanno.scale['x'])
    pre_pt_y = int(pre_pt_y * synanno.scale['y'])
    pre_pt_z = int(pre_pt_z * synanno.scale['z'])

    post_pt_x = int(post_pt_x * synanno.scale['x'])
    post_pt_y = int(post_pt_y * synanno.scale['y'])
    post_pt_z = int(post_pt_z * synanno.scale['z'])

    # create an RGB mask of the synapse from the single channel binary mask
    # colors all non zero values turquoise 
    vis_label = syn2rgb(cropped_seg_pad) # coord_0, coord_1, coord_2, c, e.g., x,y,z,3

    # draw a bright circle at the position of the pre and post synapse
    print(pre_pt_x, pre_pt_y, pre_pt_z)
    print(post_pt_x, post_pt_y, post_pt_z)
    print(vis_label.shape)
    print(coord_order)
    vis_label = draw_cylinder(vis_label, pre_pt_x, pre_pt_y, pre_pt_z, radius=10, color_1=(0, 255, 0), color_2=(200, 255, 200), layout=coord_order)
    vis_label = draw_cylinder(vis_label, post_pt_x, post_pt_y, post_pt_z, radius=10, color_1=(0, 0, 255), color_2=(200, 200, 255), layout=coord_order)

    # Determine the slice axis index based on the first entry in coord_order
    slice_axis = coord_order.index('z')

    for s in range(cropped_img_pad.shape[slice_axis]):
        img_name = str(item["Adjusted_Bbox"][slice_axis*2] + s)+".png"

        # Create a dynamic slicing tuple based on the determined slice axis
        # slice(None) is equivalent to the colon (:) operator
        slicing_img = [s if idx == slice_axis else slice(None) for idx in range(3)]
        slicing_seg = [s if idx == slice_axis else slice(None) for idx in range(4)]
        
        # image
        img_c = Image.fromarray(adjust_image_range(cropped_img_pad[tuple(slicing_img)]))
        img_c.save(os.path.join(img_dir_instance,img_name), "PNG")

        # label
        lab_c = Image.fromarray(vis_label[tuple(slicing_seg)])

        # reduce the opacity of all black pixels to zero
        lab_c = lab_c.convert("RGBA")

        lab_c = np.asarray(lab_c) 
        r, g, b, a = np.rollaxis(lab_c, axis=-1) # split into 4 n x m arrays 
        r_m = r != 0 # binary mask for red channel, True for all non black values
        g_m = g != 0 # binary mask for green channel, True for all non black values
        b_m = b != 0 # binary mask for blue channel, True for all non black values

        # combine the three binary masks by multiplying them (1*1=1, 1*0=0, 0*1=0, 0*0=0)
        # multiply the combined binary mask with the alpha channel
        a = a * ((r_m == 1) | (g_m == 1) | (b_m == 1))

        lab_c = Image.fromarray(np.dstack([r, g, b, a]), 'RGBA') # stack the img back together 

        lab_c.save(os.path.join(syn_dir_instance,img_name), "PNG")


def neuron_centric_3d_data_processing(source_url: str, target_url: str, table_name: str, preid: int = None, postid: int = None, subvolume: dict = None, bucket_secret_json: json = '~/.cloudvolume/secrets', crop_size_x: int = 148, crop_size_y: int = 148, crop_size_z: int = 16, mode: str = 'annotate', view_style: str = None) -> Union[str, Tuple[np.ndarray, np.ndarray]]:
    """ Retrieve the bounding boxes and instances indexes from the table and call the render function to render the 3D data as 2D images.

    Args:
        source_url (str): the url to the source cloud volume (EM).
        target_url (str): the url to the target cloud volume (synapse).
        table_name (str): the path to the JSON file.
        preid (int): the id of the pre synaptic region.
        postid (int): the id of the post synaptic region.
        bucket_secret_json (json): the path to the JSON file.
        patch_size (int): the size of the 2D patch.
    """
    # create the handles to the global materialization data object
    global materialization

    # retrieve the order of the coordinates (xyz, xzy, yxz, yzx, zxy, zyx)
    coordinate_order = list(synanno.coordinate_order.keys())

    # load the cloud volumes
    synanno.progress_bar_status['status'] = "Loading Cloud Volumes"
    synanno.source_cv = CloudVolume(source_url, secrets=bucket_secret_json, fill_missing=True, parallel=True)
    synanno.target_cv = CloudVolume(target_url, secrets=bucket_secret_json, fill_missing=True, parallel=True)

    # assert that both volumes have the same dimensions
    if list(synanno.source_cv.volume_size) == list(synanno.target_cv.volume_size):
        vol_dim = tuple([s-1 for s in synanno.source_cv.volume_size]) 
    else:
        # print a warning if the dimensions do not match, stating that we use the smaller size of the two volumes
        print(f"The dimensions of the source ({synanno.source_cv.volume_size}) and target ({synanno.target_cv.volume_size}) volumes do not match. We use the smaller size of the two volumes.")

        # test which size is smaller
        if np.prod(synanno.source_cv.volume_size) < np.prod(synanno.target_cv.volume_size):
            vol_dim = tuple([s-1 for s in synanno.source_cv.volume_size]) 
        else:
            vol_dim = tuple([s-1 for s in synanno.target_cv.volume_size]) 

    synanno.vol_dim = vol_dim
    synanno.vol_dim_scaled = tuple(int(a * b) for a, b in zip(vol_dim, synanno.scale.values()))
    
    # read data as dict from path table_name
    synanno.progress_bar_status['status'] = "Retrieving Materialization"

    # Read the CSV file
    df = pd.read_csv(table_name)

    if view_style == 'view':
        # should no cropping coordinates be provided, use the whole volume
        if subvolume[coordinate_order[2]+'2'] == -1:
            subvolume[coordinate_order[2]+'2'] = synanno.source_cv.info['scales'][0]['size'][2]
        
        if subvolume[coordinate_order[1]+'2'] == -1:
            subvolume[coordinate_order[1]+'2'] = synanno.source_cv.info['scales'][0]['size'][1]
       
        if subvolume[coordinate_order[0]+'2'] == -1:
            subvolume[coordinate_order[0]+'2'] = synanno.source_cv.info['scales'][0]['size'][0]
        
        # query the dataframe for all instances with their coordinates x,y,z with in the range of the subvolume
        df = df.query('x >= @subvolume["x1"] and x <= @subvolume["x2"] and y >= @subvolume["y1"] and y <= @subvolume["y2"] and z >= @subvolume["z1"] and z <= @subvolume["z2"]')

    if view_style == 'neuron':
        # TODO: This is currently a dummy solution. 
        # query the dataframe for all instances with an index between preid and postid
        if preid is None:
            preid = 0

        if postid is None:
            postid = len(df.index)

        # query the dataframe for all instances with an index between preid and postid
        df = df.query('index >= @preid and index <= @postid')

    # select only the necessary columns, save the real materialization table index as column 'index'
    df = df.reset_index()
    df = df[['index', 'pre_pt_x', 'pre_pt_y', 'pre_pt_z', 'post_pt_x', 'post_pt_y', 'post_pt_z', 'x', 'y', 'z']]

    # Convert the DataFrame to a dictionary
    bbox_dict = df.to_dict('index')

    # save the materialization to the global variable
    materialization = bbox_dict

    # number of rows in df
    session['n_images'] = len(bbox_dict.keys())

    # calculate the number of pages needed for the instance count in the JSON
    number_pages = session.get('n_images') // session.get('per_page')
    if not (session.get('n_images') % session.get('per_page') == 0):
        number_pages = number_pages + 1

    session['n_pages'] = number_pages

    return retrieve_instance_metadata(crop_size_x=crop_size_x, crop_size_y=crop_size_y, crop_size_z=crop_size_z, page=0, mode=mode)