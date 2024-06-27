const video = document.getElementById('video');
const canvas = document.getElementById('canvas');
const snap = document.getElementById('snap');
const fileInput = document.getElementById('file');
const uploadForm = document.getElementById('upload-form');

navigator.mediaDevices.getUserMedia({
    facingMode: "environment" })
    .then(stream => {
        video.srcObject = stream;
    })
    .catch(err => {
        console.error("Error accessing camera: ", err);
    });

snap.addEventListener('click', () => {
    const context = canvas.getContext('2d');
    context.drawImage(video, 0, 0, canvas.width, canvas.height);

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
