const video = document.getElementById('video');
const canvas = document.getElementById('canvas');
const snap = document.getElementById('snap');
const fileInput = document.getElementById('file');
const uploadForm = document.getElementById('upload-form');

navigator.mediaDevices.getUserMedia({ video: true })
    .then(stream => {
        video.srcObject = stream;
    })
    .catch(err => {
        console.error("Error accessing camera: ", err);
    });

snap.addEventListener('click', () => {
    const context = canvas.getContext('2d');
    context.drawImage(video, 0, 0, 640, 480);

    canvas.toBlob(blob => {
        const file = new File([blob], "photo.jpg", { type: "image/jpeg" });
        const dataTransfer = new DataTransfer();
        dataTransfer.items.add(file);
        fileInput.files = dataTransfer.files;

        // Create a new FormData object
        const formData = new FormData();
        formData.append('photo', file);

        // Send the image file to the server using fetch API
        fetch('/upload', {
            method: 'POST',
            body: formData
        })
        .then(response => {
            // Handle the response from the server
            console.log('Image uploaded successfully');
        })
        .catch(error => {
            console.error('Error uploading image:', error);
        });
    }, 'image/jpeg');
});
