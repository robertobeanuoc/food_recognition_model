const video = document.getElementById('video');
const canvas = document.getElementById('canvas');
const snap = document.getElementById('snap');
const fileInput = document.getElementById('file');
const uploadForm = document.getElementById('upload-form');

let localStream;

navigator.mediaDevices.getUserMedia({ video: {facingMode: "environment"} , width: {min:720}, height: { min: 1280} })
    .then(stream => {
        localStream = stream;
        video.srcObject = localStream;
    })
    .catch(err => {
        console.error("Error accessing camera: ", err);
    });

snap.addEventListener('click', () => {
    const context = canvas.getContext('2d');
    context.drawImage(video, 0, 0, canvas.width, canvas.height);
    document.getElementById("snap").innerHTML = "Processing...";

    canvas.toBlob(blob => {
        const formData = new FormData();
        formData.append('file', blob, 'photo.jpg');

        fetch('/upload', {
            method: 'POST',
            body: formData
        })
        .then(response => {
            return response.url;
        })  
        .then(data => {
            console.log(data);
            window.location.href = data;
        })
        .catch(error => {
            console.error('Error:', error);
        });
    }, 'image/jpeg');
});


document.addEventListener('DOMContentLoaded', function() {
    adjustCanvasSize();

    window.addEventListener('resize', adjustCanvasSize);
});

function adjustCanvasSize() {
    var canvas = document.getElementById('video');
    var width = window.innerWidth;
    var height = window.innerHeight;
    var aspectRatio = 9 / 16; // Example aspect ratio
    if (width > height) {
        aspectRatio = 16 / 9;
    }
    var aspectRatio = 9 / 16; // Example aspect ratio

    console.log('Adjusting size..');

    // Adjust stream size to 80% of window size
    // const width = window.innerWidth * 0.8;
    // const height = window.innerHeight * 0.8;
    

    // Adjust width and height according to the aspect ratio
    if (width / height > aspectRatio) {
        // If window is wider than our desired aspect ratio
        canvas.width = height * aspectRatio;
        canvas.height = height;
    } else {
        // If window is taller than our desired aspect ratio
        canvas.width = width;
        canvas.height = width / aspectRatio;
    }

    // Optional: Adjust canvas style to center it, if desired
    canvas.style.marginLeft = (window.innerWidth - canvas.width) / 2 + 'px';
    canvas.style.marginTop = (window.innerHeight - canvas.height) / 2 + 'px';
    video.srcObject.width = canvas.width * 0.95;
    video.srcObject.height = canvas.height * 0.95;

}