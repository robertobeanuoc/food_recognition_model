function updateMealSchedule(index) {
    var uuid = document.getElementById('uuid_' + index).value;
    var startTime = document.getElementById('start_time_' + index).value;
    var endTime = document.getElementById('end_time_' + index).value;

    var updated = document.getElementById('updated_' + index);

    var body = new URLSearchParams();
    body.append('start_time', startTime);
    body.append('end_time', endTime);

    fetch('/update_meal_schedule/' + uuid, {
        method: 'POST',
        credentials: 'include',
        headers: {
          'Content-Type': 'application/x-www-form-urlencoded',
        },
        body: body,
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`Request failed with status ${response.status}`);
        }
        updated.value = '';
    })
    .catch(error => {
        console.error('Error updating meal schedule:', error);
        alert('Could not save the schedule.');
    });
}
