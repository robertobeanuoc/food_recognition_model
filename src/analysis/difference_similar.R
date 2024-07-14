library(psych)
library(ggplot2)

food_comparation <- read.csv("../../data/food_compare.csv", sep = ",", stringsAsFactors = F)


describe(food_comparation$glycemic_index_difference)


ggplot(data=food_comparation,aes(x=glycemic_index_difference)) + geom_histogram()

ggplot(data=food_comparation,aes(x=glycemic_index_difference)) + geom_boxplot()
