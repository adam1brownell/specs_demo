def is_prime(n):
    """
    Check if a number is prime.
    
    Args:
        n: The number to check
        
    Returns:
        True if n is prime, False otherwise
    """
    if n < 2:
        return False
    if n == 2:
        return True
    if n % 2 == 0:
        return False
    
    # Check odd divisors up to sqrt(n)
    i = 3
    while i * i <= n:
        if n % i == 0:
            return False
        i += 2
    
    return True


if __name__ == "__main__":
    # Test with some numbers
    test_numbers = [1, 2, 3, 4, 5, 10, 11, 17, 20, 23, 29, 100, 101]
    
    for num in test_numbers:
        result = "prime" if is_prime(num) else "not prime"
        print(f"{num} is {result}")

