select
	fr.food_type,
	gi.glycemic_index,
	count(*) as count,
	avg(fr.glycemic_index-gi.glycemic_index) as diff_average,
	avg(fr.glycemic_index-gi.glycemic_index) / gi.glycemic_index * 100 as  diff_proportion,
	stddev_pop(fr.glycemic_index-gi.glycemic_index) as std_deviation

	from food_register fr 

	-- left outer
	join glycemic_index gi on gi.food_type = fr.food_type
	
	group by 
	fr.food_type,
	gi.glycemic_index

	
	
	
