const video = document.getElementById('video');
const canvas = document.getElementById('canvas');
const snap = document.getElementById('snap');
const fileInput = document.getElementById('file');
const uploadForm = document.getElementById('upload-form');

let localStream;

function startCamera() {
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
                        'Camera unavailable: ' + err2.message + '</p>';
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
            .then(response => response.url)
            .then(data => {
                console.log(data);
                window.location.href = data;
            })
            .catch(error => {
                console.error('Error:', error);
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
