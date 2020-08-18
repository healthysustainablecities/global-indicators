# Process specific script for all listed regions

script=$1
shift 
for i
do
    python "$script" "$i"
done
