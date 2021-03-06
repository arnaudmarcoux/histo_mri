import numpy as np
from os.path import basename, isfile
import matplotlib.pyplot as plt
import pickle
from colorama import Fore
import nibabel as nib
from PIL import Image, ImageDraw
from scipy.ndimage.filters import generic_filter
from skimage.filters import threshold_otsu
from scipy.ndimage.measurements import label
from skimage.morphology import binary_dilation
from skimage.morphology import binary_erosion
from skimage.transform import SimilarityTransform
from skimage.transform import warp
from sklearn.metrics.cluster import adjusted_mutual_info_score
import sys


def get_mask_data(ref, kernel_size=15, display=True):

    ref_np = nib.load(ref).get_data()

    # Computation
    measure = generic_filter(ref_np, np.std, size=kernel_size, mode='mirror')
    otsu_val = threshold_otsu(measure)
    wanted_values = measure < otsu_val
    labeled_mask, num_features = label(wanted_values)
    labeled_mask = np.array(labeled_mask)
    unique_label = np.unique(labeled_mask)
    max_number_of_px = 0
    max_label = 0
    for i, ul in enumerate(unique_label):
        if ul != 0:
            mask_lab = labeled_mask == ul
            sum_px_current_label = np.sum(mask_lab)
            if sum_px_current_label > max_number_of_px:
                max_number_of_px = sum_px_current_label
                max_label = ul
    roi = labeled_mask == max_label
    dilated_roi = binary_dilation(roi, np.ones((10, 10)))
    final_roi = binary_erosion(dilated_roi, np.ones((10, 10)))
    final_ref = np.copy(ref_np)
    final_ref[np.invert(dilated_roi)] = np.nan

    if display:
        fsize = 9
        myfig = plt.figure(3)
        myfig.suptitle("masking data for using std metrics on " + basename(ref), fontsize=fsize)

        plt.subplot(3, 3, 1)
        subplt = plt.imshow(ref_np, cmap='gray')
        subplt.axes.get_xaxis().set_visible(False)
        subplt.axes.get_yaxis().set_visible(False)
        plt.title(ref, fontsize=fsize)

        plt.subplot(3, 3, 2)
        subplt = plt.imshow(measure, cmap='gray')
        subplt.axes.get_xaxis().set_visible(False)
        subplt.axes.get_yaxis().set_visible(False)
        plt.title("std filter of " + ref + " - kernel size = " + str(kernel_size) + " x " + str(kernel_size),
                  fontsize=fsize)

        plt.subplot(3, 3, 3)
        plt.hist(measure.ravel(), bins=500, range=(np.nanmin(measure), np.nanmax(measure)), fc='k', ec='k')
        plt.title("Histogram of measure - Otsu threshold = " + str(otsu_val), fontsize=fsize)

        plt.subplot(3, 3, 4)
        subplt = plt.imshow(wanted_values, cmap='gray')
        subplt.axes.get_xaxis().set_visible(False)
        subplt.axes.get_yaxis().set_visible(False)
        plt.title("Filtered image thresholded using Otsu", fontsize=fsize)

        plt.subplot(3, 3, 5)
        subplt = plt.imshow(labeled_mask, cmap='hot')
        subplt.axes.get_xaxis().set_visible(False)
        subplt.axes.get_yaxis().set_visible(False)
        plt.title("Labelled mask - n_label = " + str(num_features), fontsize=fsize)

        plt.subplot(3, 3, 6)
        subplt = plt.imshow(roi, cmap='gray')
        subplt.axes.get_xaxis().set_visible(False)
        subplt.axes.get_yaxis().set_visible(False)
        plt.title("Extraction of largest ROI ", fontsize=fsize)

        plt.subplot(3, 3, 7)
        subplt = plt.imshow(final_roi, cmap='gray')
        subplt.axes.get_xaxis().set_visible(False)
        subplt.axes.get_yaxis().set_visible(False)
        plt.title("Flood-fill", fontsize=fsize)

        plt.subplot(3, 3, 8)
        subplt = plt.imshow(final_ref, cmap='gray')
        subplt.axes.get_xaxis().set_visible(False)
        subplt.axes.get_yaxis().set_visible(False)
        plt.title("final image", fontsize=fsize)

        plt.show()
    return final_roi


def register_histo(histo_img, preprocessed_mr_images, ref='t1', n_points=7):

    grayscale_histo = np.mean(histo_img, axis=2)
    reference = nib.load(preprocessed_mr_images.file_paths[ref]).get_data()

    myfig = plt.figure(4)
    myfig.suptitle("Select corresponding landmarks (" + str(n_points) + ") for similarity transform !")

    plt.subplot(1, 2, 1)
    plt.imshow(grayscale_histo, cmap="gray")
    x_histo = plt.ginput(n_points, timeout=0)
    print("Selected points for histological cut:")
    x_histo = np.array(x_histo)
    print(x_histo)

    plt.subplot(1, 2, 2)
    plt.imshow(reference, cmap="gray")
    x_mr = plt.ginput(n_points, timeout=0)
    print("Selected points for " + ref + ":")
    x_mr = np.array(x_mr)
    print(x_mr)

    sim_transform = SimilarityTransform()
    sim_transform.estimate(x_mr, x_histo)
    print(Fore.GREEN + "Parameter estimation - transformation matrix: " + Fore.RESET)
    print(sim_transform.params)
    warped = warp(grayscale_histo,
                  sim_transform,
                  output_shape=reference.shape)
    # grayscale_histo = grayscale_histo.astype('float32')
    return sim_transform.params, warped


def compute_nmi(preprocessed_brain, transformation_matrix):

    ref = nib.load(preprocessed_brain.file_paths["t2s"]).get_data()
    sum_of_mr = np.zeros(ref.shape, dtype=ref.dtype)
    for modality in preprocessed_brain.file_paths:
        sum_of_mr += nib.load(preprocessed_brain.file_paths[modality]).get_data()
    sum_of_mr[sum_of_mr != sum_of_mr] = 0
    grayscale_histo = np.mean(np.array(Image.open(preprocessed_brain.histo_path)), axis=2)
    w_grayscale_histo = warp(grayscale_histo, transformation_matrix, output_shape=sum_of_mr.shape)
    return adjusted_mutual_info_score(np.ravel(w_grayscale_histo.astype(int)), np.ravel(sum_of_mr.astype(int)))


def extract_idx_underlying_mask(rect_coordinates):

    min_dim = np.min(np.array(rect_coordinates), axis=0)
    max_dim = np.max(np.array(rect_coordinates), axis=0)
    bounding_box_shape = tuple((max_dim - min_dim).astype(int))
    eps = (max_dim - min_dim).astype(int) - (max_dim - min_dim)
    # need to invert coordinates for the drawing (i,j) -> (x,y)
    new_rect_coordinates = [tuple(np.array(el) - min_dim)
                            for el in rect_coordinates]
    new_rect_coordinates_xy = [elem[::-1] for elem in new_rect_coordinates]
    # Shape must indicate (width, height) so (i,j)[::-1] = (j,i) = (x,y)
    img = Image.new('1', bounding_box_shape[::-1], 0)
    ImageDraw.Draw(img).polygon(new_rect_coordinates_xy,
                                outline=0,
                                fill=1)
    idx = np.where(np.array(img))
    idx = list(idx)
    idx[0] = (idx[0] + min_dim[0] - eps[0]).astype(int)
    idx[1] = (idx[1] + min_dim[1] - eps[1]).astype(int)
    # Revert order to (i,j) convention, but this does not make any sense, because np.where is supposed
    # to give it in correct order !!
    return tuple(idx)


def save_object(obj, output_name: str):

    with open(output_name, 'wb') as output:
        pickle.dump(obj, output, pickle.HIGHEST_PROTOCOL)


def save_as_pickled_object(obj, filepath):
    """
    This is a defensive way to write pickle.write, allowing for very large files on all platforms
    """
    max_bytes = 2**31 - 1
    bytes_out = pickle.dumps(obj)
    n_bytes = sys.getsizeof(bytes_out)
    with open(filepath, 'wb') as f_out:
        for idx in range(0, n_bytes, max_bytes):
            f_out.write(bytes_out[idx:idx+max_bytes])


def load_object(filename):

    assert isinstance(filename, str), 'You must provide a str as argument of load_object function.'
    assert isfile(filename), 'The given path is not an existing file.'
    with open(filename, 'rb') as input:
        return pickle.load(input)
