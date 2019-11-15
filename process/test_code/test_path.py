import os
# os.getcwd(), notice relative path is relatived to current working directory

dirname = os.path.dirname(__file__)
txtfile = os.path.join(dirname,'../abc.txt')
print(os.getcwd())
with open(txtfile) as f:
    print(f.readlines())
