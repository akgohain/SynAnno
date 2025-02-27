# flask util functions
import datetime
import json
import logging

# manage paths and files
import os

# to zip folder
import shutil
import time

from flask import Blueprint, current_app, flash, render_template, send_file, session

# for type hinting
from jinja2 import Template

from synanno import initialize_global_variables

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# define a Blueprint for finish routes
blueprint = Blueprint("finish", __name__)


@blueprint.route("/export_annotate")
def export_annotate() -> Template:
    """Renders final view of the annotation process.

    Return:
        Export-annotate view
    """

    # disable the 'Start New Process' button as long as the user
    # did not download the masks or JSON the user can always interrupt a
    # process using the home button, but we want to prevent data loss
    return render_template("export_annotate.html", disable_snp="disabled")


@blueprint.route("/export_draw")
def export_draw() -> Template:
    """Renders final view of the draw process.

    Return:
        Export-draw view
    """

    # disable the 'Start New Process' button as long as the user did
    # not download the masks or JSON the user can always interrupt a
    # process using the home button, but we want to prevent data loss
    return render_template("export_draw.html", disable_snp="disabled")


@blueprint.route("/export_data/<string:data_type>", methods=["GET"])
def export_data(data_type) -> Template:
    """Download the JSON or the custom masks.

    Args:
        data_type: Specifies the data type for download | json, or masks

    Return:
        Either sends the JSON or the masks to the users download folder
        or rerenders the export view if there is now file that could be downloaded
    """

    with open(
        os.path.join(
            current_app.root_path,
            os.path.join(current_app.config["UPLOAD_FOLDER"]),
            current_app.config["JSON"],
        ),
        "w",
    ) as f:
        # TODO: What to do with the timing data?
        # write the metadata to a json file
        final_file = {}
        final_file["Proofread Time"] = current_app.proofread_time

        json.dump(
            current_app.df_metadata.to_dict("records"),
            f,
            indent=4,
            default=json_serial,
        )

        # provide sufficient time for the json update dependent on df_metadata
        time.sleep(0.1 * len(current_app.df_metadata))

    if data_type == "json":
        # exporting the final json
        if current_app.n_pages > 0:
            return send_file(
                os.path.join(
                    os.path.join(
                        current_app.root_path,
                        current_app.config["UPLOAD_FOLDER"],
                    ),
                    current_app.config["JSON"],
                ),
                as_attachment=True,
                download_name=current_app.config["JSON"],
            )
        else:
            flash("Now file - session data is empty.", "error")
            # rerender export-draw and enable the 'Start New Process' button
            return render_template("export_annotate.html", disable_snp=" ")
    elif data_type == "mask":
        static_folder = os.path.join(
            os.path.join(current_app.root_path, current_app.config["STATIC_FOLDER"]),
        )
        image_folder = os.path.join(static_folder, "Images")
        mask_folder = os.path.join(image_folder, "Mask")

        if os.path.exists(mask_folder):
            # create zip of folder
            shutil.make_archive(mask_folder, "zip", mask_folder)
            return send_file(
                os.path.join(image_folder, "Mask.zip"),
                as_attachment=True,
            )
        else:
            flash(
                "The folder containing custom masks is empty. "
                "Did you draw custom masks?",
                "error",
            )
            # rerender export-draw and enable the 'Start New Process' button
            return render_template("export_draw.html", disable_snp=" ")


@blueprint.route("/reset")
def reset() -> Template:
    """Resets all process by pooping the session content, resting the process bar,
    resting the timer, deleting the JSON, the images, the swcs, masks and zip folder.

    Return:
        Renders the landing-page view.
    """
    initialize_global_variables(current_app)

    # reset the session
    session.clear()

    # delete json file.
    if os.path.isfile(
        os.path.join(
            os.path.join(current_app.root_path, current_app.config["UPLOAD_FOLDER"]),
            current_app.config["JSON"],
        )
    ):
        os.remove(
            os.path.join(
                os.path.join(
                    current_app.root_path, current_app.config["UPLOAD_FOLDER"]
                ),
                current_app.config["JSON"],
            )
        )

    static_folder = os.path.join(
        current_app.root_path, current_app.config["STATIC_FOLDER"]
    )

    # delete images
    image_folder = os.path.join(static_folder, "Images")

    if os.path.exists(os.path.join(image_folder, "Img")):
        try:
            shutil.rmtree(os.path.join(image_folder, "Img"))
        except Exception as e:
            logger.error("Failed to delete %s. Reason: %s" % (image_folder, e))

    if os.path.exists(os.path.join(image_folder, "Syn")):
        try:
            shutil.rmtree(os.path.join(image_folder, "Syn"))
        except Exception as e:
            logger.error("Failed to delete %s. Reason: %s" % (image_folder, e))

    # delete swc files
    swc_folder = os.path.join(static_folder, "swc")

    if os.path.exists(swc_folder):
        try:
            shutil.rmtree(swc_folder)
        except Exception as e:
            logger.error("Failed to delete %s. Reason: %s" % (swc_folder, e))

    # delete masks zip file.
    if os.path.isfile(os.path.join(image_folder, "Mask.zip")):
        os.remove(os.path.join(image_folder, "Mask.zip"))

    # delete custom masks
    mask_folder = os.path.join(image_folder, "Mask")
    if os.path.exists(mask_folder):
        try:
            shutil.rmtree(mask_folder)
        except Exception as e:
            logger.error("Failed to delete %s. Reason: %s" % (mask_folder, e))

    return render_template("landingpage.html")


# handle non json serializable data
def json_serial(obj):
    """JSON serializer for objects not serializable by default json code"""

    if isinstance(obj, (datetime.timedelta)):
        return str(obj)
    if isinstance(obj, (datetime.datetime)):
        return obj.isoformat()
    raise TypeError("Type %s not serializable" % type(obj))
