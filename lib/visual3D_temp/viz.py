import matplotlib.pyplot as plt
import nibabel as nib
import numpy as np
import torch
import os

from lib.utils.general import prepare_input


def visualize_no_overlap(args, full_volume, affine, model, epoch, dim, writer):
    """
    this function will produce NON-overlaping  sub-volumes prediction
    that produces full 3d medical image
    compare some slices with ground truth
    :param full_volume: t1, t2, segment
    :param dim: (d1,d2,d3))
    :return: 3d reconstructed volume
    """
    print(full_volume[0].shape)
    _, slices, height, width = full_volume[0].shape

    ## TODO generalize function - currently in CPU due to memory problems
    args.cuda = False
    classes = args.classes
    model = model.eval()
    if not args.cuda:
        model = model.cpu()

    input_tensor, segment_map = create_3d_subvol(args, full_volume, dim)

    sub_volumes = input_tensor.shape[0]
    predictions = torch.tensor([]).cpu()

    # TODO generalize
    for i in range(sub_volumes):
        predicted = model(input_tensor).cpu()
        predictions = torch.cat((predictions, predicted))

    predictions = predictions.view(-1, classes, slices, height, width).detach()

    save_path_2d_fig = args.save + '/' + 'epoch__' + str(epoch).zfill(4) + '.png'
    create_2d_views(predictions, segment_map, epoch, writer, save_path_2d_fig)

    # TODO test save
    save_path = args.save + '/Pred_volume_epoch_' + str(epoch)
    save_3d_vol(predictions, affine, save_path)


def visualize_offline(args, epoch, model, full_volume, affine, writer):
    model.eval()
    test_loss = 0

    classes, slices, height, width = 4, 144, 192, 256

    predictions = torch.tensor([]).cpu()
    segment_map = torch.tensor([]).cpu()
    for batch_idx, input_tuple in enumerate(full_volume):
        with torch.no_grad():
            t1_path, t2_path, seg_path = input_tuple

            img_t1, img_t2, sub_segment_map = torch.tensor(np.load(t1_path), dtype=torch.float32)[None, None], \
                                              torch.tensor(np.load(t2_path), dtype=torch.float32)[None, None], \
                                              torch.tensor(
                                                  np.load(seg_path), dtype=torch.float32)[None]

            input_tensor, sub_segment_map = prepare_input(args, (img_t1, img_t2, sub_segment_map))
            input_tensor.requires_grad = False

            predicted = model(input_tensor).cpu()
            predictions = torch.cat((predictions, predicted))
            segment_map = torch.cat((segment_map, sub_segment_map.cpu()))

    predictions = predictions.view(-1, classes, slices, height, width).detach()
    segment_map = segment_map.view(-1, slices, height, width).detach()
    save_path_2d_fig = args.save + '/' + 'epoch__' + str(epoch).zfill(4) + '.png'

    create_2d_views(predictions, segment_map, epoch, writer, save_path_2d_fig)

    # TODO test save
    save_path = args.save + '/Pred_volume_epoch_' + str(epoch)
    save_3d_vol(predictions, affine, save_path)

    return test_loss


# TODO re-utilize prepare input here if possible
def create_3d_subvol(args, full_volume, dim):
    if args.inChannels == 3:
        img_1, img_2, img_3, target = full_volume
        print(img_1.shape)

        img_1 = torch.squeeze(img_1, dim=0).view(-1, dim[0], dim[1], dim[2])
        img_2 = img_2.view(-1, dim[0], dim[1], dim[2])
        img_3 = img_3.view(-1, dim[0], dim[1], dim[2])
        input_tensor = torch.stack((img_1, img_2, img_3), dim=1)

    elif args.inChannels == 2:
        img_1, img_2, target = full_volume

        img_1 = img_1.view(-1, dim[0], dim[1], dim[2])
        img_2 = img_2.view(-1, dim[0], dim[1], dim[2])
        input_tensor = torch.stack((img_1, img_2), dim=1)

    elif args.inChannels == 1:
        img_t1, _, target = full_volume
        input_tensor = torch.unsqueeze(img_t1, dim=1)

    return input_tensor, target


# TODO utilize and modify show_mid_slice
def create_2d_views(predictions, segment_map, epoch, writer, path_to_save):
    """
    Comparative 2d vizualization of median slices:
    axial, saggital and transpose. Save to png file and to tensorboard
    :param predictions:
    :param segment_map:
    :param epoch:
    :param writer:
    :param path_to_save:
    :return:
    """
    b, classes, slices, width, height = predictions.shape
    s = int(slices / 2.0)
    h = int(height / 2.0)
    w = int(width / 2.0)
    _, segment_pred = predictions.max(dim=1)
    segment_pred = seg_map_vizualization_iseg(segment_pred)

    s1 = segment_pred[0, s, :, :].long()
    s2 = segment_pred[0, :, w, :].long()
    s3 = segment_pred[0, :, :, h].long()

    p1 = segment_map[0, s, :, :].long()
    p2 = segment_map[0, :, w, :].long()
    p3 = segment_map[0, :, :, h].long()

    assert s1.shape == p1.shape
    assert s2.shape == p2.shape
    assert s3.shape == p3.shape

    list_vol = [s1, p1, s2, p2, s3, p3]
    rows, columns = 3, 2
    figure = plt.figure(figsize=(16, 16))
    for i in range(len(list_vol)):
        figure.add_subplot(rows, columns, i + 1)
        plt.imshow(list_vol[i], cmap='gray')

    writer.add_figure('Images/all_2d_views', figure, epoch)
    writer.add_image('Images/pred_view_1', s1, epoch, dataformats='HW')
    writer.add_image('Images/pred_view_2', s2, epoch, dataformats='HW')
    writer.add_image('Images/pred_view_3', s3, epoch, dataformats='HW')

    # TODO save image pairs
    # a1 = torch.stack((s1, p1)).long()
    # a2 = torch.stack((s2, p2)).long()
    # a3 = torch.stack((s3, p3)).long()
    # print(a1.shape,a2.shape,a3.shape)
    # writer.add_images('view_1', a1, epoch, dataformats='NHWC' )
    # writer.add_images('view_2', a2, epoch, dataformats='NHWC' )
    # writer.add_images('view_3', a3, epoch, dataformats='NHWC' )


# Todo  test!
def save_3d_vol(predictions, affine, save_path):
    # np.save(save_path+'.npy', predictions)
    pred_nifti_img = nib.Nifti1Image(predictions, affine)
    nib.save(pred_nifti_img, save_path + '.nii.gz')


def seg_map_vizualization_iseg(segmentation_map):
    # visual labels of ISEG-2017
    label_values = [0, 10, 150, 250]
    for c, j in enumerate(label_values):
        segmentation_map[segmentation_map == c] = j
    return segmentation_map


def plot_segm(segm, ground_truth, plots_dir='.'):
    """
    Saves predicted and ground truth segmentation into a PNG files (one per channel).
    :param segm: 4D ndarray (CDHW)
    :param ground_truth: 4D ndarray (CDHW)
    :param plots_dir: directory where to save the plots
    """
    import uuid
    assert segm.ndim == 4
    if ground_truth.ndim == 3:
        stacked = [ground_truth for _ in range(segm.shape[0])]
        ground_truth = np.stack(stacked)

    assert ground_truth.ndim == 4

    f, axarr = plt.subplots(1, 2)

    for seg, gt in zip(segm, ground_truth):
        mid_z = seg.shape[0] // 2

        axarr[0].imshow(seg[mid_z], cmap='prism')
        axarr[0].set_title('Predicted segmentation')

        axarr[1].imshow(gt[mid_z], cmap='prism')
        axarr[1].set_title('Ground truth segmentation')

        file_name = f'segm_{str(uuid.uuid4())[:8]}.png'
        plt.savefig(os.path.join(plots_dir, file_name))


# 2D visualization
def show_mid_slice(img_numpy):
    """
    Accepts an 3D numpy array and shows median slices in all three planes
    :param img_numpy:
    """
    assert img_numpy.ndim == 3, "please provide a 3d numpy image"
    n_i, n_j, n_k = img_numpy.shape

    # saggital
    center_i1 = int((n_i - 1) / 2)
    # transverse
    center_j1 = int((n_j - 1) / 2)
    # axial slice
    center_k1 = int((n_k - 1) / 2)

    show_slices([img_numpy[center_i1, :, :],
                 img_numpy[:, center_j1, :],
                 img_numpy[:, :, center_k1]])
    plt.suptitle("Center slices for epi_img_numpy image")


def show_slices(slices):
    """
    Function to display a row of image slices
    Input is a list of numpy 2D image slices
    """
    fig, axes = plt.subplots(1, len(slices))
    for i, slice in enumerate(slices):
        axes[i].imshow(slice.T, cmap="gray", origin="lower")
