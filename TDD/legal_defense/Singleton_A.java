/**
 * Singleton_A.java
 * Thread-safe Singleton using double-checked locking (GoF pattern).
 * This is a standard design pattern with limited expressive freedom.
 */
public class Singleton_A {

    private static volatile Singleton_A instance;
    private final String configPath;

    private Singleton_A() {
        this.configPath = "/etc/app/config.properties";
    }

    /**
     * Returns the singleton instance, creating it if necessary.
     * Uses double-checked locking for thread safety.
     */
    public static Singleton_A getInstance() {
        if (instance == null) {
            synchronized (Singleton_A.class) {
                if (instance == null) {
                    instance = new Singleton_A();
                }
            }
        }
        return instance;
    }

    public String getConfigPath() {
        return configPath;
    }
}
