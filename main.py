list = {"piekarnia":["chleb", "pączek", "bułki"], 
        "warzywniak":["marchew", "seler", "rukola"]}

new_list = dict((k.capitalize(), v) for k, v in list.items())
new_list2 = {key: [val.capitalize() for val in value] for key, value in new_list.items()}

for key, value in new_list2.items():

    print (f"Idę do {key}, kupuje tu następujące rzeczy: {value}")
length = len(list["piekarnia"])+len(list["warzywniak"])

print(f"W sumie kupuje: {length} produktów")