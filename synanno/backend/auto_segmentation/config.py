# noqa: E501

import os

import numpy as np

if "EXECUTION_ENV" not in os.environ:
    os.environ["EXECUTION_ENV"] = "local"

LOCAL_CONFIG = {
    "source_bucket_url": "gs://h01-release/data/20210601/4nm_raw",  # noqa: E501
    "target_bucket_url": "gs://h01-release/data/20210729/c3/synapses/whole_ei_onlyvol",  # noqa: E501
    "materialization_csv": "/Users/lando/Code/SynAnno/h01/synapse-export_000000000000.csv",  # noqa: E501
    "cv_secret": "~/.cloudvolume/secrets",
    "coordinate_order": ["x", "y", "z"],
    "coord_resolution_target": np.array([8, 8, 33]),
    "coord_resolution_source": np.array([4, 4, 33]),
    "UNET3D_CONFIG": {
        "in_channels": 2,
        "out_channels": 1,
        "bilinear": True,
        "features": [32, 64, 96, 128, 256],
    },
    "DATASET_CONFIG": {
        "max_workers": 8,
        "timeout": 15,
        "resize_depth": 16,
        "resize_height": 256,
        "resize_width": 256,
        "crop_size_x": 256,
        "crop_size_y": 256,
        "crop_size_z": 16,
        "slices_to_generate": 3,
        "target_range": (0, 15),
    },
    "TRAINING_CONFIG": {
        "batch_size": 1,
        "num_workers": 4,
        "pos_weight": 4.0,
        "learning_rate": 1e-4,
        "scheduler_patience": 10,
        "scheduler_gamma": 0.5,
        "num_epochs": 2,
        "patience": 20,
        "train_range": (0, 1000),
        "select_nr_train_samples": 300,
        "val_range": (1000, 1500),
        "select_nr_val_samples": 50,
        "test_range": (1500, 2000),
        "select_nr_test_samples": 1,
        "checkpoints": "/Users/lando/Code/SynAnno/synanno/backend/auto_segmentation/syn_anno_checkpoints/",  # noqa: E501
    },
}

SLURM_CONFIG = {
    "source_bucket_url": "gs://h01-release/data/20210601/4nm_raw",  # noqa: E501
    "target_bucket_url": "gs://h01-release/data/20210729/c3/synapses/whole_ei_onlyvol",  # noqa: E501
    "materialization_csv": "/mmfs1/data/lauenbur/synapse-export_000000000000.csv",  # noqa: E501
    "cv_secret": "/mmfs1/data/lauenbur/secrets",
    "coordinate_order": ["x", "y", "z"],
    "coord_resolution_target": np.array([8, 8, 33]),
    "coord_resolution_source": np.array([4, 4, 33]),
    "UNET3D_CONFIG": {
        "in_channels": 2,
        "out_channels": 1,
        "bilinear": True,
        "features": [32, 64, 96, 128, 256],
    },
    "DATASET_CONFIG": {
        "max_workers": 8,
        "timeout": 15,
        "resize_depth": 16,
        "resize_height": 256,
        "resize_width": 256,
        "crop_size_x": 256,
        "crop_size_y": 256,
        "crop_size_z": 16,
        "slices_to_generate": 3,
        "target_range": (0, 15),
    },
    "TRAINING_CONFIG": {
        "batch_size": 4,
        "num_workers": 4,
        "pos_weight": 4.0,
        "learning_rate": 5e-5,
        "scheduler_patience": 6,
        "scheduler_gamma": 0.5,
        "num_epochs": 400,
        "patience": 25,
        "train_range": (0, 5000),
        "select_nr_train_samples": 300,
        "val_range": (5000, 6000),
        "select_nr_val_samples": 50,
        "checkpoints": "/mmfs1/data/lauenbur/syn_anno_checkpoints/",  # noqa: E501
    },
}


def get_config() -> dict:
    """Get the configuration based on the execution environment.

    Returns:
        dict: The configuration dictionary.
    """
    env = os.getenv("EXECUTION_ENV", "local")
    if env == "slurm":
        return SLURM_CONFIG
    else:
        if env == "docker":
            config = LOCAL_CONFIG
            # update path to materialization csv
            config["materialization_csv"] = (
                "/app/synanno/h01/h01_104_materialization.csv"
            )
            # update path to checkpoints
            config["TRAINING_CONFIG"][
                "checkpoints"
            ] = "/app/synanno/backend/auto_segmentation/syn_anno_checkpoints/"
        return LOCAL_CONFIG
