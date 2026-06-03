package com.wildlifevn.backend.e2e;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.openqa.selenium.By;
import org.openqa.selenium.JavascriptExecutor;
import org.openqa.selenium.WebDriver;
import org.openqa.selenium.WebElement;
import org.openqa.selenium.chrome.ChromeDriver;
import org.openqa.selenium.chrome.ChromeOptions;
import org.openqa.selenium.support.ui.ExpectedConditions;
import org.openqa.selenium.support.ui.WebDriverWait;

class WildlifeFrontendE2EIT {

    private static final String FRONTEND_BASE_URL = System.getProperty(
            "frontend.baseUrl",
            System.getenv().getOrDefault("FRONTEND_BASE_URL", "http://localhost:5173"));

    @Test
    void coreUserJourneyWorksFromLibraryToChatbot() {
        ChromeOptions options = new ChromeOptions();
        options.addArguments(
                "--headless=new",
                "--disable-gpu",
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--window-size=1440,1000");

        WebDriver driver = new ChromeDriver(options);
        WebDriverWait wait = new WebDriverWait(driver, Duration.ofSeconds(90));
        try {
            driver.get(FRONTEND_BASE_URL + "/");
            waitForDocumentReady(driver, wait);
            wait.until(ExpectedConditions.visibilityOfElementLocated(By.cssSelector("[data-testid='home-shell']")));

            driver.get(FRONTEND_BASE_URL + "/library/chim");
            waitForDocumentReady(driver, wait);
            wait.until(ExpectedConditions.visibilityOfElementLocated(By.cssSelector("[data-testid='species-group-page']")));
            WebElement firstCard = wait.until(
                    ExpectedConditions.elementToBeClickable(By.cssSelector("[data-testid='species-card']")));
            firstCard.click();

            wait.until(ExpectedConditions.urlContains("/species/"));
            wait.until(ExpectedConditions.visibilityOfElementLocated(By.cssSelector("[data-testid='detail-title']")));
            driver.findElement(By.cssSelector("[data-testid='detail-chatbot-link']")).click();

            wait.until(ExpectedConditions.urlContains("/qa"));
            WebElement input = wait.until(
                    ExpectedConditions.visibilityOfElementLocated(By.cssSelector("[data-testid='chatbot-input']")));
            int initialAssistantMessages = assistantMessages(driver).size();
            input.sendKeys("Loài này có nguy cấp không?");
            driver.findElement(By.cssSelector("[data-testid='chatbot-send-button']")).click();

            wait.until(d -> assistantMessages(d).size() > initialAssistantMessages);
            assertThat(driver.getCurrentUrl()).contains("/qa");
        } finally {
            driver.quit();
        }
    }

    private static List<WebElement> assistantMessages(WebDriver driver) {
        return driver.findElements(By.cssSelector("[data-testid='chat-message-assistant']"));
    }

    private static void waitForDocumentReady(WebDriver driver, WebDriverWait wait) {
        wait.until(d -> "complete".equals(((JavascriptExecutor) d).executeScript("return document.readyState")));
    }
}
