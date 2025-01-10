import pandas as pd
import torch
from synanno.backend.auto_segmentation.dataset import SynapseDataset
from synanno.backend.auto_segmentation.config import CONFIG
from synanno.backend.auto_segmentation.match_source_and_target import (
    retrieve_smallest_volume_dim,
    compute_scale_factor,
)
from synanno.backend.auto_segmentation.retrieve_instances import setup_cloud_volume
from synanno.backend.auto_segmentation.visualize_instances import visualize_instances
from synanno.backend.auto_segmentation.trainer import Trainer
from tqdm import tqdm
from cloudvolume import CloudVolume
from typing import Any


def load_materialization_csv(csv_path: str) -> pd.DataFrame:
    """Load the materialization CSV file into a DataFrame."""
    return pd.read_csv(csv_path)


def setup_cloud_volumes() -> tuple[CloudVolume, CloudVolume]:
    """Set up CloudVolume handles for the source and target volumes."""
    source_cv = setup_cloud_volume(CONFIG["source_bucket_url"], CONFIG["cv_secret"])
    target_cv = setup_cloud_volume(CONFIG["target_bucket_url"], CONFIG["cv_secret"])
    return source_cv, target_cv


def prepare_metadata(source_cv, target_cv) -> dict[str, Any]:
    """Prepare metadata required for processing."""
    vol_dim = retrieve_smallest_volume_dim(source_cv, target_cv)
    scale = compute_scale_factor(
        CONFIG["coord_resolution_target"], CONFIG["coord_resolution_source"]
    )
    return {
        "coordinate_order": CONFIG["coordinate_order"],
        "coord_resolution_source": CONFIG["coord_resolution_source"],
        "coord_resolution_target": CONFIG["coord_resolution_target"],
        "source_cv": source_cv,
        "target_cv": target_cv,
        "scale": scale,
        "vol_dim": vol_dim,
    }


if __name__ == "__main__":
    """Main function to train and validate the model."""
    materialization_df = load_materialization_csv(
        "/Users/lando/Code/SynAnno/h01/synapse-export_000000000000.csv"
    )
    source_cv, target_cv = setup_cloud_volumes()
    meta_data = prepare_metadata(source_cv, target_cv)

    trainer = Trainer()

    print("Loading training dataset...")
    train_dataset = SynapseDataset(materialization_df, meta_data, (0, 2))

    print("Loading validation dataset...")
    val_dataset = SynapseDataset(materialization_df, meta_data, (2, 3))

    print("Running training process...")
    trainer.run_training(train_dataset, val_dataset)

    print("Loading test dataset...")
    test_dataset = SynapseDataset(materialization_df, meta_data, (0, 4))

    print("Running inference...")
    targets, predictions = trainer.run_inference("best_unet3d.pth", test_dataset)

    print("Visual result validation...")
    for tar, pred in zip(targets, predictions):
        visualize_instances(tar[0, 0, :, :, :], pred[0, 0, :, :, :], 5, 0)
        visualize_instances(tar[0, 0, :, :, :], pred[0, 0, :, :, :], 6, 0)
        visualize_instances(tar[0, 0, :, :, :], pred[0, 0, :, :, :], 7, 0)
        visualize_instances(tar[0, 0, :, :, :], pred[0, 0, :, :, :], 8, 0)
        visualize_instances(tar[0, 0, :, :, :], pred[0, 0, :, :, :], 9, 0)
        visualize_instances(tar[0, 0, :, :, :], pred[0, 0, :, :, :], 10, 0)
