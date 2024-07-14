library(psych)
library(ggplot2)

food_comparation_raw <- read.csv("../../data/food_compare.csv", sep = ",", stringsAsFactors = F)

food_comparation <- food_comparation_raw[!food_comparation_raw$glycemic_index_difference %in% "None",]
food_comparation$glycemic_index_difference = as.integer(food_comparation$glycemic_index_difference)


describe(food_comparation$glycemic_index_difference)


ggplot(data=food_comparation,aes(x=glycemic_index_difference)) + geom_histogram()

ggplot(data=food_comparation,aes(x=glycemic_index_difference)) + geom_boxplot()
