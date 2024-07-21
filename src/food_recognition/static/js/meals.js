
function updateVerified(file_uid, food_type, verified) {
    message = "file_uid=" + file_uid + "&food_type=" + food_type + "&verified=" + verified;
    let int_verified = 0;
    if (verified) {
        int_verified = 1;
    }
    const url = `/update_verified/${file_uid}/${food_type}/${int_verified}`;
    
    // Remove the extra closing curly brace
    fetch(url, {
        method: 'GET',
        credentials: 'include', // Include credentials in case of cookies/session authentication
        headers: {
          'Content-Type': 'application/json',
          // Additional headers can be added here if needed
        },
    })
    console.log(message);
}


document.addEventListener('DOMContentLoaded', (event) => {
    const datepicker = document.getElementById('datepicker');
    if (datepicker) {
        datepicker.addEventListener('input', () => {
            const date_picker = datepicker.value;
            console.log(date_picker);
            const url = `/meals/${date_picker}`;
            fetch(url, {
                method: 'POST',
                credentials: 'include', // Include credentials in case of cookies/session authentication
                headers: {
                  'Content-Type': 'application/json',
                  // Additional headers can be added here if needed
                },
            })
        });
    } else {
        console.log('Element with ID datepicker not found.');
    }
});

