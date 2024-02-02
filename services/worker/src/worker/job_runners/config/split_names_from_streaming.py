# SPDX-License-Identifier: Apache-2.0
# Copyright 2022 The HuggingFace Authors.

import logging
from typing import Optional

from datasets import get_dataset_split_names
from datasets.builder import ManualDownloadError
from datasets.data_files import EmptyDatasetError as _EmptyDatasetError
from libcommon.dtos import FullSplitItem
from libcommon.exceptions import (
    DatasetManualDownloadError,
    DatasetWithScriptNotSupportedError,
    EmptyDatasetError,
    SplitNamesFromStreamingError,
)

from worker.dtos import CompleteJobResult, SplitsList
from worker.job_runners.config.config_job_runner import ConfigJobRunnerWithDatasetsCache
from worker.utils import resolve_trust_remote_code


def compute_split_names_from_streaming_response(
    dataset: str,
    config: str,
    dataset_scripts_allow_list: list[str],
    hf_token: Optional[str] = None,
) -> SplitsList:
    """
    Get the response of 'config-split-names-from-streaming' for one specific dataset and config on huggingface.co.

    This function relies on the streaming mode if the splits are not directly defined in the dataset config. See
    https://github.dev/huggingface/datasets/blob/e183a269067575db8765ee979bd8523d14a1adae/src/datasets/inspect.py#L389-L390

    The config-split-names-from-streaming response generated by this function does not include stats about the split,
    like the size or number of samples. See dataset-info or dataset-size for that.

    Args:
        dataset (`str`):
            A namespace (user or an organization) and a repo name separated
            by a `/`.
        config (`str`):
            A configuration name.
        dataset_scripts_allow_list (`list[str]`):
            List of datasets for which we support dataset scripts.
            Unix shell-style wildcards also work in the dataset name for namespaced datasets,
            for example `some_namespace/*` to refer to all the datasets in the `some_namespace` namespace.
            The keyword `{{ALL_DATASETS_WITH_NO_NAMESPACE}}` refers to all the datasets without namespace.
        hf_token (`str`, *optional*):
            An authentication token (See https://huggingface.co/settings/token)

    Raises:
        [~`libcommon.exceptions.DatasetManualDownloadError`]:
          If the dataset requires manual download.
        [~`libcommon.exceptions.EmptyDatasetError`]:
          The dataset is empty.
        [~`libcommon.exceptions.SplitsNamesError`]:
          If the list of splits could not be obtained using the datasets library.
        [~`libcommon.exceptions.DatasetWithScriptNotSupportedError`]:
            If the dataset has a dataset script and is not in the allow list.

    Returns:
        `SplitsList`: An object with the list of split names for the dataset and config.
    """
    logging.info(f"get 'config-split-names-from-streaming' for {dataset=} {config=}")
    try:
        split_name_items: list[FullSplitItem] = [
            {"dataset": dataset, "config": config, "split": str(split)}
            for split in get_dataset_split_names(
                path=dataset,
                config_name=config,
                token=hf_token,
                trust_remote_code=resolve_trust_remote_code(dataset=dataset, allow_list=dataset_scripts_allow_list),
            )
        ]
    except ManualDownloadError as err:
        raise DatasetManualDownloadError(f"{dataset=} requires manual download.", cause=err) from err
    except _EmptyDatasetError as err:
        raise EmptyDatasetError("The dataset is empty.", cause=err) from err
    except Exception as err:
        if isinstance(err, ValueError) and "trust_remote_code" in str(err):
            raise DatasetWithScriptNotSupportedError(
                "The dataset viewer doesn't support this dataset because it runs "
                "arbitrary python code. Please open a discussion in the discussion tab "
                "if you think this is an error and tag @lhoestq and @severo."
            ) from err
        raise SplitNamesFromStreamingError(
            f"Cannot get the split names for the config '{config}' of the dataset.",
            cause=err,
        ) from err
    return SplitsList(splits=split_name_items)


class ConfigSplitNamesFromStreamingJobRunner(ConfigJobRunnerWithDatasetsCache):
    @staticmethod
    def get_job_type() -> str:
        return "config-split-names-from-streaming"

    def compute(self) -> CompleteJobResult:
        return CompleteJobResult(
            compute_split_names_from_streaming_response(
                dataset=self.dataset,
                config=self.config,
                hf_token=self.app_config.common.hf_token,
                dataset_scripts_allow_list=self.app_config.common.dataset_scripts_allow_list,
            )
        )
