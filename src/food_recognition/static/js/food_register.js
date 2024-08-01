function updateVerified(uuid, verified) {
    let int_verified = 0;
    if (verified) {
        int_verified = 1;
    }
    const url = `/update_verified/${uuid}/${int_verified}`;
    // Remove the extra closing curly brace
    fetch(url, {
        method: 'GET',
        credentials: 'include', // Include credentials in case of cookies/session authentication
        headers: {
          'Content-Type': 'application/json',
          // Additional headers can be added here if needed
        },
    })
}

function updateFoodRegister(index) 
{
    var foodType = document.getElementById('food_type_' + index).value;
    var glycemicIndex = document.getElementById('glycemic_index_' + index).value;
    var weightGrams = document.getElementById('weight_grams_' + index).value;
    var uuid = document.getElementById('uuid_' + index).value;
    var verified = document.getElementById('verified_' + index).checked ? 1 : 0;

    var updated = document.getElementById('updated_' + index);
    updated.value = '';

    console.log('foodType:', foodType, "glycemicIndex:", glycemicIndex, "uuid:", uuid);

    const url = '/update_food_register/'+ uuid + "/" +  foodType + '/' + glycemicIndex + "/" + weightGrams + "/" + verified;
    fetch(url, {
        method: 'GET',
        credentials: 'include', // Include credentials in case of cookies/session authentication
        headers: {
          'Content-Type': 'application/json',
          // Additional headers can be added here if needed
        },
    })

}