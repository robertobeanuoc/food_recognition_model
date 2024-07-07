SELECT 	sum(1) as total,
		sum(verified) as verified,
		CASE 
			WHEN sum(1) = 0 then 0  
			ELSE sum(verified) / sum(1) * 100
		END as "verified %"
		

		FROM food_register;