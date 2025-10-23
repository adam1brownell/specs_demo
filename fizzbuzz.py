def fizzbuzz(n):
    """
    Generate FizzBuzz sequence up to n.
    
    Args:
        n: The upper limit (inclusive) for the FizzBuzz sequence
        
    Returns:
        A list of FizzBuzz values
    """
    result = []
    for i in range(1, n + 1):
        if i % 15 == 0:
            result.append("FizzBuzz")
        elif i % 3 == 0:
            result.append("Fizz")
        elif i % 5 == 0:
            result.append("Buzz")
        else:
            result.append(i)
    return result


def print_fizzbuzz(n):
    """
    Print FizzBuzz sequence up to n.
    
    Args:
        n: The upper limit (inclusive) for the FizzBuzz sequence
    """
    for value in fizzbuzz(n):
        print(value)


if __name__ == "__main__":
    # Print FizzBuzz from 1 to 100
    print_fizzbuzz(100)


