const video = document.getElementById('video');
const canvas = document.getElementById('canvas');
const snap = document.getElementById('snap');
const fileInput = document.getElementById('file');
const uploadForm = document.getElementById('upload-form');

let localStream;

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
            return 'Camera access was blocked. Check your browser\'s site settings for ' +
                   'this page (usually the padlock/info icon next to the address bar) and ' +
                   'allow the camera, then reload. If it isn\'t blocked there, check your ' +
                   'device/OS settings for whether this browser app is allowed to use the ' +
                   'camera at all.';
        case 'NotFoundError':
        case 'OverconstrainedError':
            return 'No camera was found on this device.';
        case 'NotReadableError':
            return 'The camera is already in use by another app or browser tab.';
        default:
            return err.message;
    }
}

function startCamera() {
    // getUserMedia() is unavailable outside a secure context (https:// or
    // localhost) - browsers reject it with the same generic
    // "not allowed ... possibly because the user denied permission" error
    // as an actual permission block, so check this explicitly first and
    // say so, instead of leaving the user to guess which one it was.
    if (!window.isSecureContext) {
        const viewport = document.querySelector('.camera-viewport');
        if (viewport) {
            viewport.innerHTML =
                '<p style="color:white;padding:1.5rem;text-align:center;">' +
                'Camera unavailable: this page needs to be loaded over https:// ' +
                '(not http://) for camera access to work.</p>';
        }
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
                const viewport = document.querySelector('.camera-viewport');
                if (viewport) {
                    viewport.innerHTML =
                        '<p style="color:white;padding:1.5rem;text-align:center;">' +
                        'Camera unavailable: ' + cameraErrorMessage(err2) + '</p>';
                }
            });
    });
}

startCamera();

snap.addEventListener('click', () => {
    if (document.getElementById("stop_start_video").innerHTML.trim() !== "Stop Video") {
        alert("Please start the video before taking a picture.");
    } else {
        const context = canvas.getContext('2d');
        canvas.width  = video.videoWidth;
        canvas.height = video.videoHeight;
        context.drawImage(video, 0, 0, video.videoWidth, video.videoHeight);
        document.getElementById("snap").innerHTML = "Processing...";

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
                alert('Could not upload the photo.');
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
        stop_start_video.innerHTML = videoTracks[0].enabled ? 'Stop Video' : 'Start Video';
    }
}
