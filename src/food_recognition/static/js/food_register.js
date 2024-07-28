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
    console.log(message);
}