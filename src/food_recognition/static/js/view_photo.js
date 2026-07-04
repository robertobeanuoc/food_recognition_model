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

function updateCarbWeight(index) {
    var weightInput = document.getElementById('weight_grams_' + index);
    var carbPercentageInput = document.getElementById('carbohydrate_percentage_' + index);
    var carbWeightCell = document.getElementById('carbohydrate_weight_grams_' + index);

    var weight = parseFloat(weightInput.value);
    var carbPercentage = parseFloat(carbPercentageInput.value);

    if (!isNaN(weight) && !isNaN(carbPercentage)) {
        var carbWeight = (carbPercentage * weight) / 100;
        carbWeightCell.textContent = carbWeight.toFixed(1) + ' g';
    } else {
        carbWeightCell.textContent = '—';
    }
}