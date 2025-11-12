#!/bin/bash
rm dots/vector_add.svg
./main.py -i test/vector_add.csv -s test/vector_add_s.csv -c gtx1650.ini -o vector_add
if ! diff -r dots/vector_add.svg test/vector_add_ref.svg; then
    echo "Test failed"
    exit 1
fi
echo "Test passed"
exit 0
