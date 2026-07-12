function updateFoodCharacteristics(index) {
    var foodType = document.getElementById('food_type_' + index).value;
    var foodTypeEs = document.getElementById('food_type_es_' + index).value;
    var glycemicIndex = document.getElementById('glycemic_index_' + index).value;
    var carbohydratePercentage = document.getElementById('carbohydrate_percentage_' + index).value;
    var absorptionType = document.getElementById('absorption_type_' + index).value;

    var updated = document.getElementById('updated_' + index);

    var body = new URLSearchParams();
    body.append('food_type_es', foodTypeEs);
    body.append('glycemic_index', glycemicIndex);
    body.append('carbohydrate_percentage', carbohydratePercentage);
    body.append('absorption_type', absorptionType);

    fetch('/update_food_characteristics/' + encodeURIComponent(foodType), {
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
        console.error('Error updating food characteristics:', error);
        alert('Could not save the food type.');
    });
}
