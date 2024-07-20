function updateVerified(file_uid, food_type, verified) {
    message = "file_uid=" + file_uid + "&food_type=" + food_type + "&verified=" + verified;


    if (verified) {
        int_verified = 1;
    }else{
        int_verified = 0;
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