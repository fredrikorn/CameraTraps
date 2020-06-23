"""
Batch file for applying an object detection graph to a COCO style dataset,
cropping images to the detected animals inside and creating a COCO-
style classification dataset out of it. It also saves the detections
to a file using pickle
"""

import argparse
from distutils.version import StrictVersion
import json
import os
import pickle
import random
import sys
from typing import Any, Dict, List, Mapping, Optional
import uuid

import numpy as np
from PIL import Image
import pycocotools.coco
import tensorflow as tf
import tqdm

sys.path.append(
    os.path.join(
        os.path.dirname(os.path.realpath(__file__)), '../../tfrecords/utils'))
import create_tfrecords as tfr


print(
    'If you run into import errors, please make sure you added "models/research" and '
    +
    ' "models/research/object_detection" of the tensorflow models repo to the PYTHONPATH\n\n'
)

if StrictVersion(tf.__version__) < StrictVersion('1.9.0'):
    raise ImportError(
        'Please upgrade your TensorFlow installation to v1.9.* or later!')


# TFRecords variables
class TFRecordsWriter():
    """TODO"""
    def __init__(self, output_file: str, ims_per_record: int):
        self.output_file = output_file
        self.ims_per_record = ims_per_record
        self.next_shard_idx = 0
        self.next_shard_img_idx = 0
        self.coder = tfr.ImageCoder()
        self.writer = None

    def add(self, data):
        if self.next_shard_img_idx % self.ims_per_record == 0:
            if self.writer:
                self.writer.close()
            self.writer = tf.python_io.TFRecordWriter(
                self.output_file % self.next_shard_idx)
            self.next_shard_idx = self.next_shard_idx + 1
        (image_buffer, height, width) = tfr._process_image(
            data['filename'], self.coder)
        example = tfr._convert_to_example(data, image_buffer, data['height'],
                                          data['width'])
        self.writer.write(example.SerializeToString())
        self.next_shard_img_idx = self.next_shard_img_idx + 1

    def close(self):
        if self.next_shard_idx == 0 and self.next_shard_img_idx == 0:
            print('WARNING: No images were written to tfrecords!')
        if self.writer:
            self.writer.close()


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        'input_json',
        type=str,
        default='CaltechCameraTraps.json',
        help='Path to COCO-style dataset annotations')
    parser.add_argument(
        'image_dir',
        type=str,
        default='./images/cct_images',
        help='Path to root folder of images, as used in the annotations file')
    parser.add_argument(
        'frozen_graph',
        type=str,
        default='frozen_inference_graph.pb',
        help=('Frozen graph of detection network as created by '
              'export_inference_graph.py of TFODAPI.'))
    # parser.add_argument(
    #     'detections_output', type=str, default='detections_final.pkl',
    #      help='Pickle file with the detections, which can be used for cropping later on.')
    parser.add_argument(
        '--coco_style_output',
        type=str,  # default = None
        help='Output directory for a dataset in COCO format.')
    parser.add_argument(
        '--tfrecords_output',
        type=str,  # default = None
        help='Output directory for a dataset in TFRecords format.')
    parser.add_argument(
        '--location_key',
        type=str,
        default='location',
        metavar='location',
        help=('Key in the image-level annotations that specifies the splitting '
              'criteria. Usually we split camera-trap datasets by locations, '
              'i.e., training and testing locations. In this case, you '
              'probably want to pass something like `--split_by: str location`. '
              'The script prints the annotation of a randomly selected image '
              'which you can use for reference.'))
    parser.add_argument(
        '--exclude_categories',
        type=str,
        nargs='+',
        default=[],
        help=('Categories to ignore during detection. We also will not use '
              'them for the classification dataset.'))
    parser.add_argument(
        '--use_detection_file',
        type=str,  # default = None
        help=('Path to a pickle file of existing detections generated by this '
              'script. Used to continue a partially processed dataset.'))
    parser.add_argument(
        '--detection_threshold',
        type=float,
        default=0.5,
        help='Threshold for detections to use. Default is 0.5.')
    parser.add_argument(
        '--padding_factor',
        type=float,
        default=1.3 * 1.3,
        help=('We crop a tight square box around the animal enlarged by this '
              'factor. Default is 1.3 * 1.3 = 1.69, which accounts for the '
              'cropping at test time and for a reasonable amount of context.'))
        # 1.3 for the cropping during test time and 1.3 for
        # the context that the CNN requires in the left-over
        # image
    parser.add_argument(
        '--test_fraction',
        type=float,
        default=0.2,
        help='Fraction of locations used for testing, in [0, 1]. Default: 0.2')
    parser.add_argument(
        '--ims_per_record',
        type=int,
        default=200,
        help='Number of images to store in each TFRecord file')
    return parser.parse_args()


def verify_path_exists(path):
    if not os.path.exists(path):
        raise ValueError(f'{path} does not exist')


def validate_args(args: argparse.Namespace) -> str:
    """Validates arguments and creates necessary directories.

    Args:
        args: argparse.Namespace

    Returns: str, path to pickle file for saving detection output
    """
    verify_path_exists(args.input_json)
    verify_path_exists(args.image_dir)

    if args.coco_style_output is None and args.tfrecords_output is None:
        raise ValueError('Please specify at least one of --coco_style_output '
                         'or --tfrecords_output')
    if args.coco_style_output is not None:
        detection_output = os.path.join(
            args.coco_style_output, 'detections_final.pkl')
    else:
        detection_output = os.path.join(
            args.tfrecords_output, 'detections_final.pkl')

    if args.use_detection_file is not None:
        verify_path_exists(args.use_detection_file)

    if args.detection_threshold < 0 or args.detection_threshold > 1:
        raise ValueError('Detection threshold should be in [0, 1]')

    if args.padding_factor < 1:
        raise ValueError('Padding factor should be equal or larger 1')

    if args.test_fraction < 0 or args.test_fraction > 1:
        raise ValueError('test_fraction should be a value in [0, 1]')

    if args.ims_per_record <= 0:
        raise ValueError('The # of images per shard must be greater than 0')

    # Create output directories
    if args.coco_style_output is not None:
        print('Creating COCO-style dataset output directory.')
        os.makedirs(args.coco_style_output, exist_ok=True)
    if args.tfrecords_output is not None:
        print('Creating TFRecords output directory.')
        os.makedirs(args.tfrecords_output, exist_ok=True)

    return detection_output


def load_frozen_graph(graph_path: str) -> tf.Graph:
    """Load TensorFlow model into memory

    Args:
        graph_path: str, path to saved TensorFlow model

    Returns: tf.Graph
    """
    graph = tf.Graph()
    with graph.as_default():
        od_graph_def = tf.GraphDef()
        with tf.io.gfile.GFile(graph_path, 'rb') as fid:
            serialized_graph = fid.read()
            od_graph_def.ParseFromString(serialized_graph)
            tf.import_graph_def(od_graph_def, name='')
    return graph


def main(input_json: str,
         image_dir: str,
         coco_output_dir: Optional[str],
         tfrecords_output_dir: Optional[str],
         detection_output: str,
         detection_input: Optional[str],
         split_by: str,
         exclude_categories: List[str],
         detection_threshold: float,
         padding_factor: float,
         test_fraction: float,
         ims_per_record: int):
    """
    Args:
        input_json: str, path to JSON file with COCO-style dataset annotations
        image_dir: str, path to root folder of images
        coco_output_dir: str, path to output directory for a dataset in COCO
            format
        tfrecords_output_dir: str, path to output directory for a dataset in
            TFRecords format
        detection_output: str, path to pickle file for saving detections
        detection_input: str, path to pickle file of existing detections
            generated by this script, used to continue a partially processed
            dataset
        split_by: str, key in image-level annotations that specifies the
            splitting criteria
        exclude_categories: list of str, names of categories to ignore during
            detection
        detection_threshold: float, in [0, 1]
        padding_factor: float, padding around detected objects when cropping
        test_fraction: float, in [0, 1]
        ims_per_record: int
    """
    tmp_image = str(uuid.uuid4()) + '.jpg'

    graph = load_frozen_graph(args.frozen_graph)

    # Load COCO style annotations from the input dataset
    coco = pycocotools.coco.COCO(input_json)

    # Get all categories, their names, and create updated ID for the json file
    categories = coco.loadCats(coco.getCatIds())
    cat_id_to_names = {cat['id']: cat['name'] for cat in categories}
    cat_id_to_new_id = {
        old_key: idx
        for idx, old_key in enumerate(cat_id_to_names.keys())
    }
    print('All categories: \n"{}"\n'.format('", "'.join(cat_id_to_names.values())))
    for ignore_cat in exclude_categories:
        if ignore_cat not in cat_id_to_names.values():
            raise ValueError(f'Category {ignore_cat} does not exist in dataset')

    # Prepare the coco-style json files
    train_json = dict(images=[], categories=[], annotations=[])
    test_json = dict(images=[], categories=[], annotations=[])

    for old_cat_id in cat_id_to_names.keys():
        train_json['categories'].append(
            dict(id=cat_id_to_new_id[old_cat_id],
                 name=cat_id_to_names[old_cat_id],
                 supercategory='entity'))
    test_json['categories'] = train_json['categories']

    # Split the dataset by locations
    random.seed(0)
    print('Example of the annotation of a single image:')
    print(list(coco.imgs.items())[0])
    print('The corresponding category annoation:')
    print(coco.imgToAnns[list(coco.imgs.items())[0][0]])
    locations = sorted(set(ann[split_by] for ann in coco.imgs.values()))
    test_locations = sorted(
        random.sample(locations, max(1, int(test_fraction * len(locations)))))
    train_locations = sorted(set(locations) - set(test_locations))
    print('{} locations in total, {} for training, {} for testing'.format(
        len(locations), len(train_locations), len(test_locations)))
    print('Training uses locations ', train_locations)
    print('Testing uses locations ', test_locations)

    # Load detections
    if detection_input is not None:
        print(f'Loading existing detections from {detection_input}')
        with open(detection_input, 'rb') as f:
            detections = pickle.load(f)
    else:
        detections = dict()

    if tfrecords_output_dir is not None:
        training_tfr_writer = TFRecordsWriter(
            os.path.join(tfrecords_output_dir, 'train-%.5d'), ims_per_record)
        test_tfr_writer = TFRecordsWriter(
            os.path.join(tfrecords_output_dir, 'test-%.5d'), ims_per_record)
    else:
        training_tfr_writer = None
        test_tfr_writer = None

    with graph.as_default():
        with tf.Session() as sess:
            run_detection(
                sess, coco, cat_id_to_names, cat_id_to_new_id, detections,
                train_locations, train_json, test_json, image_dir,
                coco_output_dir, tfrecords_output_dir, split_by,
                exclude_categories, detection_threshold, padding_factor)

    if tfrecords_output_dir:
        training_tfr_writer.close()
        test_tfr_writer.close()

        label_map = []
        for cat in train_json['categories']:
            label_map += [
                'item {{name: "{}" id: {}}}\n'.format(cat['name'], cat['id'])
            ]
        pbtxt_path = os.path.join(tfrecords_output_dir, 'label_map.pbtxt')
        with open(pbtxt_path, 'w') as f:
            f.write(''.join(label_map))

    if coco_output_dir is not None:
        # Write out COCO-style json files to the output directory
        with open(os.path.join(coco_output_dir, 'train.json'), 'wt') as fi:
            json.dump(train_json, fi)
        with open(os.path.join(coco_output_dir, 'test.json'), 'wt') as fi:
            json.dump(test_json, fi)

    # Write detections to file with pickle
    with open(detection_output, 'wb') as f:
        pickle.dump(detections, f, pickle.HIGHEST_PROTOCOL)


def run_detection(sess: tf.Session,
                  coco: pycocotools.coco.COCO,
                  cat_id_to_names: Mapping[Any, str],
                  cat_id_to_new_id: Mapping[Any, int],
                  detections: Dict,  # TODO
                  train_locations: List[str],
                  train_json: Dict[str, List],
                  test_json: Dict[str, List],
                  image_dir: str,
                  coco_output_dir: Optional[str],
                  tfrecords_output_dir: Optional[str],
                  split_by: str,
                  exclude_categories: List[str],
                  detection_threshold: float,
                  padding_factor: float):
    """
    Args:
        sess: tf.Session
        coco: pycocotools.coco.COCO, representation of JSON
        cat_id_to_names: dict, maps "old" category IDs to names
        cat_id_to_new_id: dict, maps "old" category IDs to new IDs
        detections: dict, TODO
        train_locations: list of str, TODO
        train_json: dict, TODO
        test_json: dict, TODO
        **for all other args, see description for main()
    """
    images_missing = False

    graph = tf.get_default_graph()

    ### Preparations: get all the output tensors
    ops = graph.get_operations()
    all_tensor_names = {output.name for op in ops for output in op.outputs}
    tensor_dict = {}
    for key in ['num_detections', 'detection_boxes', 'detection_scores',
                'detection_classes']:
        tensor_name = key + ':0'
        if tensor_name in all_tensor_names:
            tensor_dict[key] = graph.get_tensor_by_name(tensor_name)
    if 'detection_masks' in tensor_dict:
        # The following processing is only for single image
        detection_boxes = tf.squeeze(tensor_dict['detection_boxes'], [0])
        # Reframe is required to translate mask from box coordinates to image coordinates and fit the image size.
        real_num_detection = tf.cast(tensor_dict['num_detections'][0],
                                        tf.int32)
        detection_boxes = tf.slice(detection_boxes, [0, 0],
                                    [real_num_detection, -1])
    image_tensor = graph.get_tensor_by_name('image_tensor:0')

    # For all images listed in the annotations file
    next_image_id = 0
    next_annotation_id = 0
    for image_id in tqdm.tqdm(sorted(vv['id'] for vv in coco.imgs.values())):
        detect_single_img(image_id, train_locations, tensor_dict, image_tensor, sess, coco, cat_id_to_names, cat_id_to_new_id, detections, train_json, test_json, image_dir, coco_output_dir, tfrecords_output_dir, split_by, exclude_categories, detection_threshold, padding_factor)


def detect_single_img(image_id: str,
                      train_locations: List[str],
                      tensor_dict: Mapping[str, tf.Tensor],
                      image_tensor: tf.Tensor,
                      sess: tf.Session,
                      coco: pycocotools.coco.COCO,
                      cat_id_to_names: Mapping[Any, str],
                      cat_id_to_new_id: Mapping[Any, int],
                      detections: Dict,  # TODO
                      train_json: Dict[str, List],
                      test_json: Dict[str, List],
                      image_dir: str,
                      coco_output_dir: Optional[str],
                      tfrecords_output_dir: Optional[str],
                      split_by: str,
                      exclude_categories: List[str],
                      detection_threshold: float,
                      padding_factor: float):
    """
    Args
        image_id: str,
        train_locations: List[str],
        tensor_dict: Mapping[str, tf.Tensor],
        image_tensor: tf.Tensor,
        **for all other args, see description for run_detection()
    """
    category_ids = {ann['category_id'] for ann in coco.imgToAnns[image_id]}

    # Skip the image if it is annotated with more than one category
    if len(category_ids) != 1:
        return

    # Get "old" category ID, category name, and "new" category ID for this image
    cat_id = list(category_ids)[0]
    cat_name = cat_id_to_names[cat_id]
    json_cat_id = cat_id_to_new_id[cat_id]

    # Skip excluded categories
    if cat_name in exclude_categories:
        return

    cur_image = coco.loadImgs([image_id])[0]

    # get path to image
    cur_file_name = cur_image['file_name']
    in_file = os.path.join(image_dir, cur_file_name)

    # whether it belongs to a training or testing location
    is_train = cur_image[split_by] in train_locations

    # If we already have detection results, we can use them
    if image_id in detections.keys():
        output_dict = detections[image_id]
    # Otherwise run detector
    else:
        # We allow to skip images, which we do not have available right now
        # This is useful for processing parts of large datasets
        if not os.path.isfile(in_file):
            if not images_missing:
                print('Could not find:', in_file)
                print('Suppressing further warnings about missing files.')
                images_missing = True
            return

        # Load image
        image = np.array(Image.open(in_file))
        if image.dtype != np.uint8:
            print('Failed to load image:', in_file)
            return

        # Run inference
        output_dict = sess.run(tensor_dict, feed_dict={
            image_tensor: np.expand_dims(image, 0)
        })

        # all outputs are float32 numpy arrays, so convert types as appropriate
        output_dict['num_detections'] = int(
            output_dict['num_detections'][0])
        output_dict['detection_classes'] = output_dict[
            'detection_classes'][0].astype(np.uint8)
        output_dict['detection_boxes'] = output_dict[
            'detection_boxes'][0]
        output_dict['detection_scores'] = output_dict[
            'detection_scores'][0]
        if 'detection_masks' in output_dict:
            output_dict['detection_masks'] = output_dict[
                'detection_masks'][0]

        # Add detections to the collection
        detections[image_id] = output_dict

    imsize = cur_image['width'], cur_image['height']
    # Select detections with a confidence larger DETECTION_THRESHOLD
    selection = output_dict['detection_scores'] > detection_threshold
    # Skip if no detection selected
    if np.sum(selection) < 1 or selection.size == 0:
        return
    # Get these boxes and convert normalized coordinates to pixel coordinates
    selected_boxes = (output_dict['detection_boxes'][selection] *
                      np.tile([imsize[1], imsize[0]], (1, 2)))
    # Pad the detected animal to a square box and additionally by PADDING_FACTOR, the result will be in crop_boxes
    # However, we need to make sure that it box coordinates are still within the image
    bbox_sizes = np.vstack([
        selected_boxes[:, 2] - selected_boxes[:, 0],
        selected_boxes[:, 3] - selected_boxes[:, 1]
    ]).T
    offsets = (
        padding_factor * np.max(bbox_sizes, axis=1, keepdims=True) -
        bbox_sizes) / 2
    crop_boxes = selected_boxes + np.hstack([-offsets, offsets])
    crop_boxes = np.maximum(0, crop_boxes).astype(int)
    # For each detected bounding box with high confidence, we will
    # crop the image to the padded box and save it
    for box_id in range(selected_boxes.shape[0]):
        # bbox is the detected box, crop_box the padded / enlarged box
        bbox, crop_box = selected_boxes[box_id], crop_boxes[box_id]
        if coco_output_dir is not None:
            # The file path as it will appear in the annotation json
            new_file_name = os.path.join(cat_name, cur_file_name)
            # Add numbering to the original file name if there are multiple boxes
            if selected_boxes.shape[0] > 1:
                new_file_base, new_file_ext = os.path.splitext(new_file_name)
                new_file_name = f'{new_file_base}_{box_id}{new_file_ext}'
            # The absolute file path where we will store the image
            # Only used if an coco-style dataset is created
            out_file = os.path.join(coco_output_dir, new_file_name)
            # Create the category directories if necessary
            os.makedirs(os.path.dirname(out_file), exist_ok=True)
            if not os.path.exists(out_file):
                try:
                    img = np.array(Image.open(in_file))
                    cropped_img = img[crop_box[0]:crop_box[2],
                                      crop_box[1]:crop_box[3]]
                    Image.fromarray(cropped_img).save(out_file)
                except ValueError:
                    continue
                except FileNotFoundError:
                    continue
            else:
                # if COCO_OUTPUT_DIR is set, then we will only use the shape
                # of cropped_img in the following code. So instead of reading
                # cropped_img = np.array(Image.open(out_file))
                # we can speed everything up by reading only the size of the image
                cropped_img = np.zeros((3, ) + Image.open(out_file).size).T
        else:
            out_file = TMP_IMAGE
            try:
                img = np.array(Image.open(in_file))
                cropped_img = img[crop_box[0]:crop_box[2],
                                  crop_box[1]:crop_box[3]]
                Image.fromarray(cropped_img).save(out_file)
            except ValueError:
                continue
            except FileNotFoundError:
                continue

        # Read the image
        if coco_output_dir is not None:
            # Add annotations to the appropriate json
            if is_train:
                cur_json = train_json
                cur_tfr_writer = training_tfr_writer
            else:
                cur_json = test_json
                cur_tfr_writer = test_tfr_writer
            cur_json['images'].append(
                dict(id=next_image_id,
                     width=cropped_img.shape[1],
                     height=cropped_img.shape[0],
                     file_name=new_file_name,
                     original_key=image_id))
            cur_json['annotations'].append(
                dict(id=next_annotation_id,
                     image_id=next_image_id,
                     gory_id=json_cat_id))

        if tfrecords_output_dir is not None:
            image_data = {
                'id': next_image_id,
                'class': {'label': json_cat_id,
                          'text': cat_name},
                'height': cropped_img.shape[0],
                'width': cropped_img.shape[1]
            }
            if coco_output_dir is not None:
                image_data['filename'] = out_file
            else:
                Image.fromarray(cropped_img).save(TMP_IMAGE)
                image_data['filename'] = TMP_IMAGE

            cur_tfr_writer.add(image_data)
            if coco_output_dir is None:
                os.remove(TMP_IMAGE)

        next_annotation_id = next_annotation_id + 1
        next_image_id = next_image_id + 1


if __name__ == '__main__':
    args = parse_args()
    detection_output = validate_args(args)
    main(input_json=args.input_json,
         image_dir=args.image_dir,
         coco_output_dir=args.coco_style_output,
         tfrecords_output_dir=args.tfrecords_output,
         detection_output=detection_output,
         detection_input=args.use_detection_file,
         split_by=args.location_key,
         exclude_categories=args.exclude_categories,
         detection_threshold=args.detection_threshold,
         padding_factor=args.padding_factor,
         test_fraction=args.test_fraction,
         ims_per_record=args.ims_per_record)
