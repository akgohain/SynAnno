# import global configs
import synanno


# flask util functions
from flask import render_template, request, jsonify

# flask ajax requests
from flask_cors import cross_origin

# update the json file
import json

# track the annotation time
import datetime

# for type hinting
from jinja2 import Template
from typing import Dict


# global variable defining if instances marked as false positives are directly discarded
global delete_fps

delete_fps = False

from flask import Blueprint
from flask import current_app as app


# define a Blueprint for categorize routes
blueprint = Blueprint("categorize", __name__)


@blueprint.route("/categorize")
def categorize() -> Template:
    """Stop the annotation timer, start the categorization timer, and render the categorize view

    Return:
        Categorization view that enables the user the specify the fault of instance masks
        marked as "Incorrect" or "Unsure".
    """

    # stop the annotation timer
    if app.proofread_time["finish_grid"] is None:
        if app.proofread_time["start_grid"] is None:
            app.proofread_time[
                "difference_grid"
            ] = "Non linear execution of the grid process - time invalid"
        else:
            app.proofread_time["finish_grid"] = datetime.datetime.now()
            app.proofread_time["difference_grid"] = (
                app.proofread_time["finish_grid"] - app.proofread_time["start_grid"]
            )
    # start the categorization timer
    if app.proofread_time["start_categorize"] is None:
        app.proofread_time["start_categorize"] = datetime.datetime.now()

    output_dict = app.df_metadata[
        app.df_metadata["Label"].isin(["Incorrect", "Unsure"])
    ].to_dict("records")

    # retrieve the data for the current page
    return render_template("categorize.html", images=output_dict)


@blueprint.route("/pass_flags", methods=["GET", "POST"])
@cross_origin()
def pass_flags() -> Dict[str, object]:
    """Serves an Ajax request from categorize.js, retrieving the new error tags from the
    frontend and updating metadata data frame.

    Return:
        Confirms the successful update to the frontend
    """

    # variable specifying if instances marked as FP are discarded, the default is False
    global delete_fps

    # retrieve the frontend data
    flags = request.get_json()["flags"]
    delete_fps = bool(request.get_json()["delete_fps"])

    # updated all flags
    for flag in flags:
        page_nr, img_nr, f = dict(flag).values()
        # deleting false positives
        if f == "falsePositive" and delete_fps:
            app.df_metadata.drop(
                app.df_metadata[
                    (app.df_metadata["Page"] == int(page_nr))
                    & (app.df_metadata["Image_Index"] == int(img_nr))
                ].index,
                inplace=True,
            )
        else:
            app.df_metadata.loc[
                (app.df_metadata["Page"] == int(page_nr))
                & (app.df_metadata["Image_Index"] == int(img_nr)),
                "Error_Description",
            ] = f

    # stop the time for the proofreading process
    if app.proofread_time["finish_categorize"] is None:
        app.proofread_time["finish_categorize"] = datetime.datetime.now()
        app.proofread_time["difference_categorize"] = (
            app.proofread_time["finish_categorize"]
            - app.proofread_time["start_categorize"]
        )

    # returning a JSON formatted response to trigger the ajax success logic
    return json.dumps({"success": True}), 200, {"ContentType": "application/json"}


@blueprint.route("/custom_flag", methods=["GET", "POST"])
@cross_origin()
def custom_flag() -> Dict[str, object]:
    """Serves an Ajax request from categorize.js, retrieving the custom error message."""

    # used by frontend to retrieve custom error messages from the JSON
    page = request.get_json()["page"]
    img_id = request.get_json()["img_id"]
    data = app.df_metadata.loc(
        (app.df_metadata["Page"] == page) & (app.df_metadata["Image_Index"] == img_id),
        "Error_Description",
    ).to_dict("records")[0]
    data = json.dumps(data)
    return jsonify(message=data)
