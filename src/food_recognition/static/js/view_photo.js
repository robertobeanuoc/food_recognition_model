function updateGlycemicIndex(index) {

    var foodTypeInput = document.getElementById('food_type_' + index);
    console.log('foodType called with index:', foodTypeInput);

    var url = '/glycemic_index/' + foodTypeInput.value;
    fetch(url)
        .then(response => response.text())
        .then(data => {
            var glycemicIndexInput = document.getElementById('glycemic_index_' + index);
            console.log('updateGlycemicIndex called with index:', glycemicIndexInput);
            glycemicIndexInput.value = data;
        })
        .catch(error => {
            console.error('Error:', error);
        });
}