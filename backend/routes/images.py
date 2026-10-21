"""
Image Upload & Storage Routes (Stage 6)
---------------------------------------
Handles secure image upload, verification, storage, and retrieval for events.
Only organizers who own an approved event can upload photographs of the event location.
All images are validated against allowed types (.jpg, .jpeg, .png) and content integrity,
saved to the filesystem with unique names, and registered in MySQL with status 'pending'.
"""

import os
import uuid
import logging
from datetime import datetime, timedelta
from typing import Any
from flask import Blueprint, request, jsonify, session, g, send_from_directory, current_app
from PIL import Image

from config.settings import settings
from middleware.auth import require_auth, require_role
from models.event import EventModel
from models.image import ImageModel
from models.crowd_analysis import CrowdAnalysisModel
from models.alert import AlertModel

logger = logging.getLogger(__name__)
images_bp = Blueprint('images', __name__)



def serialize_field(val: Any) -> Any:
    """Serializes date, time, datetime, and timedelta values safely for JSON."""
    if hasattr(val, 'isoformat'):
        return val.isoformat()
    if isinstance(val, timedelta):
        total_sec = int(val.total_seconds())
        hours = total_sec // 3600
        minutes = (total_sec % 3600) // 60
        seconds = total_sec % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return val


def serialize_data(obj: Any) -> Any:
    """Recursively serializes list and dict structures."""
    if isinstance(obj, list):
        return [serialize_data(item) for item in obj]
    if isinstance(obj, dict):
        return {k: serialize_field(v) for k, v in obj.items()}
    return serialize_field(obj)


def is_blank_or_uniform_image(image_input) -> bool:
    """
    Detects whether an image is completely blank or uniform (all pixels have identical color).
    Accepts either an open PIL Image or a filesystem path.
    Uses C-accelerated getextrema() over RGB channels to verify pixel spread.
    An image is uniform if all color channels have zero variance (min == max).
    Accommodates subtle JPEG DCT quantization noise where channel spread is <= 1.
    Ordinary photographs with real-world scenes, lighting, and sensor noise
    will always have channel spreads significantly greater than 1.
    """
    close_after = False
    if isinstance(image_input, (str, os.PathLike)):
        img = Image.open(image_input)
        close_after = True
    else:
        img = image_input

    try:
        rgb = img.convert('RGB')
        extrema = rgb.getextrema()
        # extrema is ((min_r, max_r), (min_g, max_g), (min_b, max_b))
        return all((max_v - min_v) <= 1 for min_v, max_v in extrema)
    finally:
        if close_after:
            img.close()


# -------------------------------------------------------------
# 1. UPLOAD EVENT IMAGE
# -------------------------------------------------------------
@images_bp.route('/events/<int:event_id>/images', methods=['POST'])
@require_role('organizer')
def upload_event_image(event_id: int):
    """
    Upload an event-place photograph for an approved event.
    Strictly isolated: only the event owner (organizer) can upload.
    Validates file format, size, and content integrity before storage.
    """
    organizer_id = session.get('user_id')

    # 1. Verify Event Exists
    event = EventModel.get_by_id(event_id)
    if not event:
        return jsonify({
            "error": "Not Found",
            "message": "Event not found."
        }), 404

    # 2. Verify Event Ownership
    if event['organizer_id'] != organizer_id:
        return jsonify({
            "error": "Forbidden",
            "message": "Access denied. You can only upload images for your own events."
        }), 403

    # 3. Verify Event Status and Active Happening Schedule (Management final approved schedule)
    is_happening, reason = EventModel.is_event_happening(event)
    if not is_happening:
        return jsonify({
            "error": "Bad Request",
            "message": reason
        }), 400

    # 4. Check File Presence
    if 'image' not in request.files:
        return jsonify({
            "error": "Bad Request",
            "message": "Please select an image to upload."
        }), 400

    file = request.files['image']
    if not file or not file.filename or not file.filename.strip():
        return jsonify({
            "error": "Bad Request",
            "message": "Please select an image to upload."
        }), 400

    filename = file.filename.strip()

    # 5. Validate File Extension
    if '.' not in filename:
        return jsonify({
            "error": "Bad Request",
            "message": "Unsupported image format. Allowed formats: JPG, JPEG, PNG."
        }), 400

    ext = filename.rsplit('.', 1)[-1].lower()
    if ext not in settings.ALLOWED_IMAGE_EXTENSIONS:
        return jsonify({
            "error": "Bad Request",
            "message": "Unsupported image format. Allowed formats: JPG, JPEG, PNG."
        }), 400

    # 6. Validate File Size
    file.seek(0, os.SEEK_END)
    file_size = file.tell()
    file.seek(0)

    if file_size > settings.MAX_CONTENT_LENGTH:
        return jsonify({
            "error": "Bad Request",
            "message": "Image size exceeds the maximum allowed limit (10 MB)."
        }), 400

    if file_size == 0:
        return jsonify({
            "error": "Bad Request",
            "message": "Uploaded image file is empty."
        }), 400

    # 7. Validate Image Content Integrity using Pillow
    try:
        img = Image.open(file)
        img.verify()
        if img.format.upper() not in ('JPEG', 'PNG'):
            return jsonify({
                "error": "Bad Request",
                "message": "The uploaded file is not a valid JPEG or PNG image."
            }), 400
        # Reset file stream position after verify
        file.seek(0)
    except Exception:
        return jsonify({
            "error": "Bad Request",
            "message": "The uploaded file is not a valid image."
        }), 400

    # 8. Generate Safe Unique Filename
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_suffix = uuid.uuid4().hex[:8]
    normalized_ext = 'jpg' if ext == 'jpeg' else ext
    safe_filename = f"event_{event_id}_{timestamp}_{unique_suffix}.{normalized_ext}"

    # Ensure upload directory exists
    os.makedirs(settings.UPLOAD_FOLDER, exist_ok=True)
    abs_filepath = os.path.join(settings.UPLOAD_FOLDER, safe_filename)

    # 9. Save Image to Filesystem
    try:
        file.save(abs_filepath)
    except Exception as save_err:
        return jsonify({
            "error": "Internal Server Error",
            "message": f"Failed to save image file: {str(save_err)}"
        }), 500

    # 10. Record Metadata in MySQL Database
    rel_db_path = f"uploads/event_images/{safe_filename}"
    try:
        image_id = ImageModel.create_image(
            event_id=event_id,
            image_path=rel_db_path,
            processing_status='pending'
        )
    except Exception as db_err:
        # Atomic consistency: cleanup orphan file if database insert fails
        if os.path.exists(abs_filepath):
            try:
                os.remove(abs_filepath)
            except OSError:
                pass
        return jsonify({
            "error": "Internal Server Error",
            "message": "Failed to store image record in database."
        }), 500

    return jsonify({
        "success": True,
        "message": "Image uploaded successfully.",
        "image": {
            "id": image_id,
            "event_id": event_id,
            "image_path": rel_db_path,
            "image_url": f"/uploads/event_images/{safe_filename}",
            "processing_status": "pending",
            "uploaded_at": datetime.now().isoformat()
        }
    }), 201


# -------------------------------------------------------------
# 2. LIST IMAGES FOR AN EVENT
# -------------------------------------------------------------
@images_bp.route('/events/<int:event_id>/images', methods=['GET'])
@require_auth
def get_event_images(event_id: int):
    """
    Retrieve all uploaded images for a specific event.
    Organizers can only access their own event's images.
    Administrators can access any event's images.
    """
    event = EventModel.get_by_id(event_id)
    if not event:
        return jsonify({
            "error": "Not Found",
            "message": "Event not found."
        }), 404

    # Authorization Check
    user = g.current_user
    if user['role'] == 'organizer' and event['organizer_id'] != user['id']:
        return jsonify({
            "error": "Forbidden",
            "message": "Access denied. You can only view images for your own events."
        }), 403

    raw_images = ImageModel.get_images_by_event(event_id)

    # Format images with image_url for direct rendering
    formatted_images = []
    for img in raw_images:
        filename = os.path.basename(img['image_path'])
        formatted_images.append({
            "id": img.get('image_id') or img.get('id'),
            "event_id": img['event_id'],
            "image_path": img['image_path'],
            "image_url": f"/uploads/event_images/{filename}",
            "uploaded_at": serialize_field(img.get('uploaded_at')),
            "processing_status": img['processing_status'],
            "predicted_count": img.get('predicted_count'),
            "analysis_timestamp": serialize_field(img.get('analysis_timestamp'))
        })

    return jsonify({
        "success": True,
        "event_id": event_id,
        "total_images": len(formatted_images),
        "images": formatted_images
    }), 200


# -------------------------------------------------------------
# 3. SAFE FILE SERVING
# -------------------------------------------------------------
def serve_event_image_direct(filename: str):
    """Safely serves uploaded event image files."""
    return send_from_directory(settings.UPLOAD_FOLDER, filename)


@images_bp.route('/uploads/event_images/<path:filename>', methods=['GET'])
def serve_event_image(filename: str):
    """
    Safely serves uploaded event image files from the designated upload folder.
    Flask's send_from_directory prevents directory traversal attacks.
    """
    return serve_event_image_direct(filename)


# -------------------------------------------------------------
# 4. CROWD ANALYSIS INFERENCE ENDPOINTS (Stage 7)
# -------------------------------------------------------------
def _execute_crowd_analysis(image_id: int, event_id: Any = None):
    """
    Core implementation of crowd analysis on an uploaded event image.
    - Verifies image and event existence.
    - Strictly enforces role-based authorization (organizer ownership or administrator).
    - Checks that event is in 'approved' status.
    - Validates file presence and content integrity on server storage.
    - Executes CSRNet predictor via thread-safe lazy singleton.
    - Persists predicted headcount and processing status in crowd_analyses and images tables.
    """
    # 1. Verify Image Exists
    image = ImageModel.get_by_id(image_id)
    if not image:
        return jsonify({
            "error": "Not Found",
            "message": "Image not found."
        }), 404

    # 2. Verify Event Association if event_id is supplied in route
    if event_id is not None and image['event_id'] != event_id:
        return jsonify({
            "error": "Bad Request",
            "message": "The specified image does not belong to this event."
        }), 400

    # 3. Verify Event Exists
    event = EventModel.get_by_id(image['event_id'])
    if not event:
        return jsonify({
            "error": "Not Found",
            "message": "Associated event not found."
        }), 404

    # 4. Role-based Authorization
    user = g.current_user
    user_role = user.get('role')
    effective_admin = {'administrator', 'management'}

    if user_role == 'organizer':
        if event['organizer_id'] != user['id']:
            return jsonify({
                "error": "Forbidden",
                "message": "Access denied. You can only analyze images for your own events."
            }), 403
    elif user_role not in effective_admin:
        return jsonify({
            "error": "Forbidden",
            "message": f"Access denied. Unauthorized role '{user_role}'."
        }), 403

    # 5. Verify Event Status (Approved events only)
    if event.get('status') != 'approved':
        return jsonify({
            "error": "Bad Request",
            "message": (
                f"Crowd analysis can only be requested for approved events. "
                f"Current event status is '{event.get('status')}'."
            )
        }), 400

    # 6. Safely Resolve File Path on Server Storage
    raw_path = image.get('image_path', '')
    filename = os.path.basename(raw_path)
    abs_filepath = os.path.join(settings.UPLOAD_FOLDER, filename)

    existing_analysis = CrowdAnalysisModel.get_by_image_id(image_id)
    has_prior_completed = (
        existing_analysis is not None and
        existing_analysis.get('processing_status') == 'completed'
    )

    if not filename or not os.path.isfile(abs_filepath):
        if not has_prior_completed:
            ImageModel.update_processing_status(image_id, 'failed')
        return jsonify({
            "error": "Not Found",
            "message": "Image file not found on server storage."
        }), 404

    # 7. Validate Image File Integrity with Pillow
    try:
        with Image.open(abs_filepath) as test_img:
            test_img.verify()
    except Exception:
        if not has_prior_completed:
            ImageModel.update_processing_status(image_id, 'failed')
        return jsonify({
            "error": "Unprocessable Entity",
            "message": "The image file on server storage is invalid or corrupted."
        }), 422

    # 7b. Check for Completely Blank or Uniform Image (e.g. solid-color test images)
    try:
        with Image.open(abs_filepath) as test_img:
            if is_blank_or_uniform_image(test_img):
                if not has_prior_completed:
                    ImageModel.update_processing_status(image_id, 'failed')
                return jsonify({
                    "error": "Unprocessable Entity",
                    "message": "The uploaded photograph appears to be blank or completely uniform. Please upload a valid event photograph showing the crowd or venue."
                }), 422
    except Exception:
        if not has_prior_completed:
            ImageModel.update_processing_status(image_id, 'failed')
        return jsonify({
            "error": "Unprocessable Entity",
            "message": "The image file on server storage is invalid or corrupted."
        }), 422

    # 8. Set Processing Status
    ImageModel.update_processing_status(image_id, 'processing')

    # 9. Perform Inference via CSRNet Predictor Lazy Singleton
    try:
        from ai.predictor import get_default_predictor, CrowdPredictor
        predictor = get_default_predictor()
        result = predictor.predict(abs_filepath)

        # Record detailed inference diagnostics in server logs (not in public UI)
        logger.info(
            CrowdPredictor.format_diagnostics_log(
                result,
                identifier=f"Image ID: {image_id}, Event ID: {event.get('id')}"
            )
        )
    except Exception as exc:
        logger.error(
            "Crowd analysis inference failed for image ID %s: %s",
            image_id,
            exc,
            exc_info=True
        )
        if not has_prior_completed:
            ImageModel.update_processing_status(image_id, 'failed')
            try:
                CrowdAnalysisModel.upsert_analysis(
                    image_id=image_id,
                    predicted_count=0,
                    processing_status='failed',
                    model_name='CSRNet'
                )
            except Exception:
                pass

        return jsonify({
            "error": "Internal Server Error",
            "message": "Crowd analysis model inference failed. Please try again later."
        }), 500

    # 10. Persist Result in Database
    try:
        predicted_count = result["predicted_count"]
        model_name = result.get("model_name", "CSRNet")

        analysis_id = CrowdAnalysisModel.upsert_analysis(
            image_id=image_id,
            predicted_count=predicted_count,
            processing_status='completed',
            model_name=model_name
        )
        ImageModel.update_processing_status(image_id, 'completed')
        analysis_record = CrowdAnalysisModel.get_by_id(analysis_id)

        # Trigger automated crowd safety alert if detected count >= threshold
        try:
            AlertModel.evaluate_and_create_alerts(
                event_id=event["id"],
                crowd_analysis_id=analysis_id,
                predicted_count=predicted_count
            )
        except Exception as alert_err:
            logger.error(
                "Failed to evaluate crowd safety alert for analysis %s: %s",
                analysis_id,
                alert_err,
                exc_info=True
            )
    except Exception as db_err:
        ImageModel.update_processing_status(image_id, 'failed')
        return jsonify({
            "error": "Internal Server Error",
            "message": "Failed to store crowd analysis record in database."
        }), 500

    return jsonify({
        "success": True,
        "message": "Crowd analysis completed successfully.",
        "analysis": {
            "id": analysis_record["id"],
            "image_id": image_id,
            "event_id": event["id"],
            "predicted_count": predicted_count,
            "processing_status": "completed",
            "model_name": model_name,
            "analysis_timestamp": serialize_field(analysis_record["analysis_timestamp"]),
            "density_stats": result.get("density_stats")
        }
    }), 200


@images_bp.route('/images/<int:image_id>/analyze', methods=['POST'])
@require_auth
def analyze_image_direct(image_id: int):
    """Trigger CSRNet crowd estimation on an uploaded event image by image ID."""
    return _execute_crowd_analysis(image_id=image_id)


@images_bp.route('/events/<int:event_id>/images/<int:image_id>/analyze', methods=['POST'])
@require_auth
def analyze_event_image(event_id: int, image_id: int):
    """Trigger CSRNet crowd estimation on an uploaded event image with event verification."""
    return _execute_crowd_analysis(image_id=image_id, event_id=event_id)


@images_bp.route('/images/<int:image_id>/analysis', methods=['GET'])
@require_auth
def get_image_analysis(image_id: int):
    """
    Retrieve existing crowd analysis results for a specific image.
    Organizers can only access analyses for their own events.
    Administrators can access any analysis.
    """
    image = ImageModel.get_by_id(image_id)
    if not image:
        return jsonify({
            "error": "Not Found",
            "message": "Image not found."
        }), 404

    event = EventModel.get_by_id(image['event_id'])
    if not event:
        return jsonify({
            "error": "Not Found",
            "message": "Associated event not found."
        }), 404

    user = g.current_user
    user_role = user.get('role')
    effective_admin = {'administrator', 'management'}

    if user_role == 'organizer':
        if event['organizer_id'] != user['id']:
            return jsonify({
                "error": "Forbidden",
                "message": "Access denied. You can only view analysis for your own events."
            }), 403
    elif user_role not in effective_admin:
        return jsonify({
            "error": "Forbidden",
            "message": "Access denied."
        }), 403

    analysis = CrowdAnalysisModel.get_by_image_id(image_id)
    if not analysis:
        return jsonify({
            "error": "Not Found",
            "message": "No crowd analysis found for this image."
        }), 404

    return jsonify({
        "success": True,
        "analysis": {
            "id": analysis["id"],
            "image_id": image_id,
            "event_id": event["id"],
            "predicted_count": analysis["predicted_count"],
            "processing_status": analysis["processing_status"],
            "model_name": analysis["model_name"],
            "analysis_timestamp": serialize_field(analysis["analysis_timestamp"])
        }
    }), 200

