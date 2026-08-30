function updateMealDefaultItem(index) {
    var uuid = document.getElementById('uuid_' + index).value;
    var foodType = document.getElementById('food_type_' + index).value;
    var weightGrams = document.getElementById('weight_grams_' + index).value;

    var updated = document.getElementById('updated_' + index);

    var body = new URLSearchParams();
    body.append('food_type', foodType);
    body.append('weight_grams', weightGrams);

    fetch('/update_meal_default_item/' + uuid, {
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
        console.error('Error updating meal default item:', error);
        alert(window.__I18N__.save_default_item_failed);
    });
}

function deleteMealDefaultItem(uuid, button) {
    if (!confirm(window.__I18N__.delete_default_item_confirm)) {
        return;
    }

    fetch('/delete_meal_default_item/' + uuid, {
        method: 'DELETE',
        credentials: 'include',
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`Request failed with status ${response.status}`);
        }
        const row = button.closest('tr');
        if (row) {
            row.remove();
        }
    })
    .catch(error => {
        console.error('Error deleting meal default item:', error);
        alert(window.__I18N__.delete_default_item_failed);
    });
}

function addMealDefaultItem() {
    var mealType = document.getElementById('new_meal_type').value;
    var dayOfWeek = document.getElementById('new_day_of_week').value;
    var presetOrder = document.getElementById('new_preset_order').value;
    var itemOrder = document.getElementById('new_item_order').value;
    var foodType = document.getElementById('new_food_type').value;
    var weightGrams = document.getElementById('new_weight_grams').value;

    if (!foodType) {
        alert(window.__I18N__.enter_food_type);
        return;
    }

    var body = new URLSearchParams();
    body.append('meal_type', mealType);
    body.append('day_of_week', dayOfWeek);
    body.append('preset_order', presetOrder);
    body.append('item_order', itemOrder);
    body.append('food_type', foodType);
    body.append('weight_grams', weightGrams);

    fetch('/add_meal_default_item', {
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
        location.reload();
    })
    .catch(error => {
        console.error('Error adding meal default item:', error);
        alert(window.__I18N__.add_default_item_failed);
    });
}
