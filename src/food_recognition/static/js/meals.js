



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

