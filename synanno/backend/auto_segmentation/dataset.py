import logging
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import numpy as np
import pandas as pd
import torch
import torchvision.transforms as transforms
from torch.utils.data import Dataset
from tqdm import tqdm

from synanno.backend.auto_segmentation.config import get_config
from synanno.backend.auto_segmentation.model_source_data import generate_seed_target
from synanno.backend.auto_segmentation.retrieve_instances import (
    retrieve_instance_from_cv,
    retrieve_instance_metadata,
    setup_cloud_volume,
)

CONFIG = get_config()

# Retrieve logger
logger = logging.getLogger(__name__)


def normalize_tensor(tensor: torch.Tensor, max_value: int = 255) -> torch.Tensor:
    """
    Normalize a tensor to [0, 1].

    Args:
        tensor (torch.Tensor): Target tensor.

    Returns:
        torch.Tensor: Normalized target tensor.
    """
    return tensor / max_value


def binarize_tensor(tensor: torch.Tensor) -> torch.Tensor:
    """
    Binarize a tensor.

    Args:
        tensor (torch.Tensor): Target tensor.

    Returns:
        torch.Tensor: Binarized target tensor.
    """
    return (tensor > 0.5).float()


class SynapseDataset(Dataset):
    """Dataset for synapse images and targets."""

    def __init__(
        self,
        materialization_df: pd.DataFrame,
        meta_data: dict[str, Any],
        synapse_id_range: tuple[int, int],
        select_nr_from_range: int = 0,
        transform: Any = None,
        target_transform: Any = None,
    ) -> None:
        """
        Initialize the SynapseDataset.

        Args:
            materialization_df: DataFrame containing materialization data.
            meta_data: Metadata dictionary.
            synapse_id_range: Range of synapse IDs to include in the dataset.
            select_nr_from_range: Number of synapse IDs to select from the range.
            transform: Transform to apply to the source data. Defaults to None.
            target_transform: Transform to apply to the target data. Defaults to None.
        """
        self.materialization_df = materialization_df
        self.meta_data = meta_data
        self.transform = transform
        self.target_transform = target_transform

        # Randomly select a subset of the ids from the id range
        if (
            select_nr_from_range > 0
            and select_nr_from_range < synapse_id_range[1] - synapse_id_range[0]
        ):
            self.selected_ids = np.random.choice(
                range(synapse_id_range[0], synapse_id_range[1]),
                select_nr_from_range,
                replace=False,
            )
        else:
            self.selected_ids = range(synapse_id_range[0], synapse_id_range[1])

        self.max_workers = CONFIG["DATASET_CONFIG"]["max_workers"]
        self.timeout = CONFIG["DATASET_CONFIG"]["timeout"]
        self.resize_depth = CONFIG["DATASET_CONFIG"]["resize_depth"]
        self.resize_height = CONFIG["DATASET_CONFIG"]["resize_height"]
        self.resize_width = CONFIG["DATASET_CONFIG"]["resize_width"]
        self.crop_size_x = CONFIG["DATASET_CONFIG"]["crop_size_x"]
        self.crop_size_y = CONFIG["DATASET_CONFIG"]["crop_size_y"]
        self.crop_size_z = CONFIG["DATASET_CONFIG"]["crop_size_z"]
        self.slices_to_generate = CONFIG["DATASET_CONFIG"]["slices_to_generate"]
        self.target_range = CONFIG["DATASET_CONFIG"]["target_range"]
        self.dataset = self._generate_dataset()

    def _generate_dataset(self) -> list[dict[str, Any]]:
        """
        Generate the dataset by retrieving instances and processing them.

        Returns:
            list: list of dictionaries containing dataset instances.
        """
        instance_list = []
        for idx in tqdm(
            self.selected_ids,
            desc="Metadata Retrieval",
        ):
            instance = retrieve_instance_metadata(
                idx,
                self.materialization_df,
                CONFIG["coordinate_order"],
                self.crop_size_x,
                self.crop_size_y,
                self.crop_size_z,
                self.meta_data["vol_dim"],
            )
            instance_list.append(instance)

        instance_meta_data_df = pd.DataFrame(instance_list)
        instance_meta_data_list_of_dics = instance_meta_data_df.sort_values(
            by="Image_Index"
        ).to_dict("records")

        dataset = []
        lock = threading.Lock()  # Lock for thread-safe appending

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [
                executor.submit(retrieve_instance_from_cv, item, self.meta_data)
                for item in instance_meta_data_list_of_dics
            ]
            for future in tqdm(
                as_completed(futures),
                total=len(futures),
                desc="Data Retrieval",
            ):
                try:
                    result = future.result(timeout=self.timeout)
                    with lock:  # Ensure thread-safe addition to the dataset
                        dataset.append(result)
                    logger.info("Successfully retrieved data sample.")
                except Exception as exc:
                    logger.error(f"An exception occurred during data retrieval: {exc}")
                    # Retry logic
                    try:
                        result = future.result(timeout=self.timeout)
                        with lock:
                            dataset.append(result)
                        logger.info("Successfully retrieved data sample after retry")
                    except Exception as exc:
                        logger.error(f"Retry failed with error: {exc}")
                        traceback.print_exc()

        logger.info(f"Finished data retrieval with {len(dataset)} items.")

        # Seed/Target Generation
        for sample in tqdm(dataset, desc="Seed/Target Generation"):
            seed_volume, selected_seed_slices = generate_seed_target(
                sample["target"], self.slices_to_generate, self.target_range
            )
            # sample["source_seed_target"] = seed_volume
            sample["source"] = np.stack([sample["source_image"], seed_volume], axis=-1)
            sample["selected_slices"] = selected_seed_slices

        return dataset

    def __len__(self) -> int:
        """
        Get the length of the dataset.

        Returns:
            int: Length of the dataset.
        """
        return len(self.dataset)

    def __getitem__(self, idx: int) -> tuple[torch.Tensor, torch.Tensor]:
        """
        Retrieve a source and target sample from the dataset.

        Args:
            idx: Index of the sample to retrieve.

        Returns:
            tuple[torch.Tensor, torch.Tensor]: Source and target tensors.
        """
        sample = self.dataset[idx]
        source = sample["source"]  # Shape: (x, y, z, 2)
        target = sample["target"]  # Shape: (x, y, z)

        # Convert to tensors and permute the dimensions
        source = torch.tensor(source, dtype=torch.float32).permute(
            3, 2, 0, 1
        )  # Shape: (2, D, H, W)
        target = torch.tensor(target, dtype=torch.float32).permute(
            2, 0, 1
        )  # Shape: (D, H, W)

        image_channel = source[0]  # Shape: (D, H, W)
        mask_channel = source[1]  # Shape: (D, H, W)

        # Add a channel dimension
        image_channel = image_channel.unsqueeze(0)  # Shape: (1, D, H, W)
        mask_channel = mask_channel.unsqueeze(0)  # Shape: (1, D, H, W)
        target = target.unsqueeze(0)  # Shape: (1, D, H, W)

        # Add a batch dimension
        image_channel = image_channel.unsqueeze(0)  # Shape: (1, 1, D, H, W)
        mask_channel = mask_channel.unsqueeze(0)  # Shape: (1, 1, D, H, W)
        target = target.unsqueeze(0)  # Shape: (1, 1, D, H, W)

        image_channel = torch.nn.functional.interpolate(
            image_channel,
            size=(
                self.resize_depth,
                self.resize_height,
                self.resize_width,
            ),
            mode="trilinear",
            align_corners=False,
        )
        mask_channel = torch.nn.functional.interpolate(
            mask_channel,
            size=(
                self.resize_depth,
                self.resize_height,
                self.resize_width,
            ),
            mode="nearest",
        )
        target = torch.nn.functional.interpolate(
            target,
            size=(
                self.resize_depth,
                self.resize_height,
                self.resize_width,
            ),
            mode="nearest",
        )

        # Collapse the batch dimension
        image_channel = image_channel.squeeze(0)  # Shape: (1, D, H, W)
        mask_channel = mask_channel.squeeze(0)  # Shape: (1, D, H, W)
        target = target.squeeze(0)  # Shape: (1, D, H, W)

        # Combine and normalize
        source = torch.cat([image_channel, mask_channel], dim=0)  # Shape: (2, D, H, W)
        source[0] = normalize_tensor(source[0])  # Normalize the image channel
        source[1] = binarize_tensor(source[1])  # Binarize the seed mask
        target = binarize_tensor(target)  # Binarize the target

        if self.transform:
            seed = (
                torch.random.seed()
            )  # Get a random seed to apply the same transform to both input and target
            torch.random.manual_seed(seed)
            source = self.transform(source)
            torch.random.manual_seed(seed)
            target = self.transform(target)

        return source, target


class RandomRotation90:
    def __call__(self, sample: torch.Tensor) -> torch.Tensor:
        if torch.rand(1).item() > 0.75:  # Apply rotation 25% of the time
            angles = [90, -90]
            angle = np.random.choice(angles)
            return torch.rot90(sample, k=angle // 90, dims=[-2, -1])
        return sample


if __name__ == "__main__":
    from synanno.backend.auto_segmentation.match_source_and_target import (
        compute_scale_factor,
        retrieve_smallest_volume_dim,
    )
    from synanno.backend.auto_segmentation.visualize_instances import (
        visualize_instances,
    )

    # Load the materialization csv
    materialization_df = pd.read_csv(
        "/Users/lando/Code/SynAnno/h01/synapse-export_000000000000.csv"
    )

    # Set up CV handles to the source and target volume
    source_cv = setup_cloud_volume(CONFIG["source_bucket_url"], CONFIG["cv_secret"])
    target_cv = setup_cloud_volume(CONFIG["target_bucket_url"], CONFIG["cv_secret"])

    vol_dim = retrieve_smallest_volume_dim(source_cv, target_cv)
    scale = compute_scale_factor(
        CONFIG["coord_resolution_target"], CONFIG["coord_resolution_source"]
    )

    meta_data = {
        "coordinate_order": CONFIG["coordinate_order"],
        "coord_resolution_source": CONFIG["coord_resolution_source"],
        "coord_resolution_target": CONFIG["coord_resolution_target"],
        "source_cv": source_cv,
        "target_cv": target_cv,
        "scale": scale,
        "vol_dim": vol_dim,
    }

    # Define the transformations
    data_transforms = transforms.Compose(
        [
            transforms.RandomHorizontalFlip(),
            transforms.RandomVerticalFlip(),
            RandomRotation90(),
        ]
    )

    train_dataset = SynapseDataset(
        materialization_df, meta_data, (0, 2), transform=data_transforms
    )

    # Retrieve a training sample
    sample = train_dataset[0]

    # Validate the shape
    assert sample[0].shape == (
        2,
        16,
        256,
        256,
    ), f"Sample input shape: {sample[0].shape}"
    assert sample[1].shape == (
        1,
        16,
        256,
        256,
    ), f"Sample target shape: {sample[1].shape}"

    # Validate the value ranges
    assert (
        torch.min(sample[0][0, :, :, :]) == 0.0
    ), f"Min value image channel: {torch.min(sample[0][0,:,:,:])}"
    assert (
        torch.max(sample[0][0, :, :, :]) == 1.0
    ), f"Max value image channel: {torch.max(sample[0][0,:,:,:])}"
    assert len(torch.unique(sample[0][0, :, :, :])) > 1, (
        "Number of unique values in the image channel:"
        f"{torch.unique(sample[0][0,:,:,:])}"
    )

    assert (
        torch.min(sample[0][1, :, :, :]) == 0.0
    ), f"Min value seed channel: {torch.min(sample[0][1,:,:,:])}"
    assert (
        torch.max(sample[0][1, :, :, :]) == 1.0
    ), f"Max value seed channel: {torch.max(sample[0][1,:,:,:])}"
    assert len(torch.unique(sample[0][1, :, :, :])) == 2, (
        "Number of unique values in the seed channel: "
        f"{torch.unique(sample[0][1,:,:,:])}"
    )
    assert torch.sum(sample[0][1, :, :, :] > 0) > 0, (
        "Number of non-zero values in the seed channel: "
        "{torch.sum(sample[0][1,:,:,:] > 0)}"
    )

    assert (
        torch.min(sample[1][0, :, :, :]) == 0.0
    ), f"Min value target: {torch.min(sample[1][0,:,:,:])}"
    assert (
        torch.max(sample[1][0, :, :, :]) == 1.0
    ), f"Max value target: {torch.max(sample[1][0,:,:,:])}"
    assert (
        len(torch.unique(sample[1][0, :, :, :])) == 2
    ), f"Number of unique values in the target: {torch.unique(sample[1][0,:,:,:])}"
    assert torch.sum(sample[1][0, :, :, :] > 0) > 0, (
        "Number of non-zero values in the target sample: "
        "{torch.sum(sample[1][0,:,:,:] > 0)}"
    )

    assert torch.sum(sample[0][1, :, :, :] > 0) < torch.sum(
        sample[1][0, :, :, :] > 0
    ), "The target should have more non-zero values than the seed channel."

    # Visualize the first non-zero seed segmentation slice
    visualize_instances(
        sample[0][0, :, :, :],
        (sample[0][1, :, :, :].numpy() * 255).astype(np.uint8),
        train_dataset.dataset[0]["selected_slices"][0],
        0,
    )
    visualize_instances(
        (sample[0][1, :, :, :].numpy() * 255).astype(np.uint8),
        (sample[1][0, :, :, :].numpy() * 255).astype(np.uint8),
        train_dataset.dataset[0]["selected_slices"][0],
        0,
    )
