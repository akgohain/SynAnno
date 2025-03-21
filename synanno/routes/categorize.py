import datetime
import json

from flask import Blueprint, current_app, render_template, request
from flask_cors import cross_origin

# Define a Blueprint for categorize routes
blueprint = Blueprint("categorize", __name__)


@blueprint.route("/categorize")
def categorize():
    """Render the categorize view.

    Returns:
        Categorization view that enables the user to specify the fault
        of instance masks marked as "incorrect" or "unsure".
    """
    stop_annotation_timer()
    start_categorization_timer()

    output_dict = current_app.df_metadata[
        current_app.df_metadata["Label"].isin(["incorrect", "unsure"])
    ].to_dict("records")

    return render_template(
        "categorize.html",
        images=output_dict,
        neuron_id=current_app.selected_neuron_id,
        neuronReady=current_app.neuron_ready,
    )


def stop_annotation_timer():
    """Stop the annotation timer."""
    if current_app.proofread_time["finish_grid"] is None:
        if current_app.proofread_time["start_grid"] is None:
            current_app.proofread_time["difference_grid"] = (
                "Non linear execution of the grid process - time invalid"
            )
        else:
            current_app.proofread_time["finish_grid"] = datetime.datetime.now()
            current_app.proofread_time["difference_grid"] = (
                current_app.proofread_time["finish_grid"]
                - current_app.proofread_time["start_grid"]
            )


def start_categorization_timer():
    """Start the categorization timer."""
    if current_app.proofread_time["start_categorize"] is None:
        current_app.proofread_time["start_categorize"] = datetime.datetime.now()


@blueprint.route("/pass_flags", methods=["GET", "POST"])
@cross_origin()
def pass_flags():
    """Serves an Ajax request from categorize.js, retrieving the new error tags from the
    frontend and updating metadata data frame.

    Returns:
        Confirms the successful update to the frontend
    """
    flags = request.get_json()["flags"]
    delete_fps = bool(request.get_json()["delete_fps"])

    update_flags(flags, delete_fps)
    stop_categorization_timer()

    return (
        json.dumps({"success": True}),
        200,
        {"ContentType": "application/json"},
    )


def update_flags(flags, delete_fps):
    """Update the flags in the metadata DataFrame.

    Args:
        flags: List of flags to update.
        delete_fps: Boolean indicating if false positives should be deleted.
    """
    for flag in flags:
        page_nr, img_nr, error_flag = dict(flag).values()

        # remove unwanted quotation marks; the pragmatically set the
        # False Negative flag it will be set as "False Negative"
        error_flag = error_flag.replace('"', "")
        error_flag = error_flag.replace("'", "")

        if error_flag == "falsePositive" and delete_fps:
            current_app.df_metadata.drop(
                current_app.df_metadata[
                    (current_app.df_metadata["Page"] == int(page_nr))
                    & (current_app.df_metadata["Image_Index"] == int(img_nr))
                ].index,
                inplace=True,
            )
        else:
            current_app.df_metadata.loc[
                (current_app.df_metadata["Page"] == int(page_nr))
                & (current_app.df_metadata["Image_Index"] == int(img_nr)),
                "Error_Description",
            ] = error_flag


def stop_categorization_timer():
    """Stop the categorization timer."""
    if current_app.proofread_time["finish_categorize"] is None:
        current_app.proofread_time["finish_categorize"] = datetime.datetime.now()
        current_app.proofread_time["difference_categorize"] = (
            current_app.proofread_time["finish_categorize"]
            - current_app.proofread_time["start_categorize"]
        )
