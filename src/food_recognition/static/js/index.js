const video = document.getElementById('video');
const canvas = document.getElementById('canvas');
const snap = document.getElementById('snap');
const fileInput = document.getElementById('file');
const uploadForm = document.getElementById('upload-form');

let localStream;
let videoRunning = true;

// The browser's own getUserMedia() error names, translated into something
// the user can actually act on - the raw DOMException message (e.g.
// "The request is not allowed by the user agent or the platform in the
// current context, possibly because the user denied permission.") is
// Chrome's stock text for NotAllowedError, which fires for both "you
// clicked Block" and "this page isn't a secure context" - indistinguishable
// to the user without this.
function cameraErrorMessage(err) {
    switch (err.name) {
        case 'NotAllowedError':
        case 'SecurityError':
            return window.__I18N__.camera_blocked;
        case 'NotFoundError':
        case 'OverconstrainedError':
            return window.__I18N__.camera_not_found;
        case 'NotReadableError':
            return window.__I18N__.camera_in_use;
        default:
            return err.message;
    }
}

// Shown as plain page text below the camera box (not overlaid on top of
// the black video viewport, which has its own styling/effects that made an
// error message written there hard to read).
function showCameraError(message) {
    const errorBox = document.getElementById('camera-error');
    if (errorBox) {
        errorBox.textContent = window.__I18N__.camera_unavailable + message;
        errorBox.classList.remove('d-none');
    }
}

function startCamera() {
    // getUserMedia() is unavailable outside a secure context (https:// or
    // localhost) - browsers reject it with the same generic
    // "not allowed ... possibly because the user denied permission" error
    // as an actual permission block, so check this explicitly first and
    // say so, instead of leaving the user to guess which one it was.
    if (!window.isSecureContext) {
        showCameraError(window.__I18N__.camera_insecure_context);
        return;
    }

    navigator.mediaDevices.getUserMedia({
        video: {
            facingMode: { ideal: "environment" },
            width:  { ideal: 2048 },
            height: { ideal: 1536 }
        }
    })
    .then(stream => {
        localStream = stream;
        video.srcObject = localStream;
    })
    .catch(err => {
        console.warn("Preferred camera settings failed, trying fallback:", err);
        navigator.mediaDevices.getUserMedia({ video: true })
            .then(stream => {
                localStream = stream;
                video.srcObject = localStream;
            })
            .catch(err2 => {
                console.error("Error accessing camera:", err2);
                showCameraError(cameraErrorMessage(err2));
            });
    });
}

startCamera();

snap.addEventListener('click', () => {
    if (!videoRunning) {
        alert(window.__I18N__.start_video_first);
    } else {
        const context = canvas.getContext('2d');
        canvas.width  = video.videoWidth;
        canvas.height = video.videoHeight;
        context.drawImage(video, 0, 0, video.videoWidth, video.videoHeight);
        document.getElementById("snap").innerHTML = window.__I18N__.processing;

        canvas.toBlob(blob => {
            const formData = new FormData();
            formData.append('file', blob, 'photo.jpg');

            fetch('/upload', {
                method: 'POST',
                body: formData
            })
            .then(response => {
                if (response.status === 401) {
                    window.location.href = '/login';
                    return null;
                }
                if (!response.ok) {
                    throw new Error(`Request failed with status ${response.status}`);
                }
                return response.url;
            })
            .then(data => {
                if (data) {
                    console.log(data);
                    window.location.href = data;
                }
            })
            .catch(error => {
                console.error('Error:', error);
                alert(window.__I18N__.upload_failed);
            });
        }, 'image/jpeg');

        stop_start_video_function();
    }
});

stop_start_video.addEventListener('click', () => {
    stop_start_video_function();
});

function stop_start_video_function() {
    if (localStream) {
        const videoTracks = localStream.getVideoTracks();
        videoTracks[0].enabled = !videoTracks[0].enabled;
        videoRunning = videoTracks[0].enabled;
        stop_start_video.innerHTML = videoRunning ? window.__I18N__.stop_video : window.__I18N__.start_video;
    }
}
